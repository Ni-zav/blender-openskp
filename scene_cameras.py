"""Saved SketchUp page cameras, decoded by OpenSKP without the NEOS SDK.

Legacy page records are locally validated, matching the upstream page scanner
approach. Unknown camera layouts fail explicitly instead of inventing views.
"""
import math
import struct
from pathlib import Path
import bpy
from mathutils import Matrix, Vector


def legacy_pages(data):
    from openskp.legacy import _R, _STR_MARKER
    pages = []
    pos = 0
    while True:
        index = data.find(_STR_MARKER, pos)
        if index < 0: break
        pos = index + 3
        try:
            reader = _R(data, index)
            name = reader.utf16()
            if not name or len(name) > 200 or any(ord(c) < 32 for c in name): continue
            if reader.utf16() != '': continue
            flags = reader.u32()
            # Capture bit 0 stores the camera. Known page masks fit 16 bits.
            if not flags & 1 or flags > 0xffff: continue
            tag = reader.u16()
            if tag == 0xffff:
                reader.u16(); size = reader.u16()
                if reader.raw(size) != b'CCamera': continue
            elif not tag & 0x8000:
                continue
            start = reader.pos
            values = struct.unpack_from('<11d', data, start)
            perspective = data[start + 88]
            fov, height = struct.unpack_from('<2d', data, start + 89)
            if perspective not in (0, 1) or not 0 < fov < 180: continue
            if not all(math.isfinite(v) for v in (*values, fov, height)): continue
            eye, target, up = values[:3], values[3:6], values[6:9]
            if not .5 < Vector(up).length < 1.5 or (Vector(target)-Vector(eye)).length < 1e-9: continue
            pages.append(dict(name=name, eye=eye, target=target, up=up,
                              fov=fov, parallel=not perspective, ortho_height=height,
                              clip=values[9:11]))
        except (ValueError, IndexError, struct.error, UnicodeError):
            continue
    return pages


def pages_from_file(filepath, parsed):
    from openskp.legacy import is_legacy
    with open(filepath, 'rb') as handle: header=handle.read(512)
    if is_legacy(header):
        pages = legacy_pages(Path(filepath).read_bytes())
        # The upstream scanner can identify pages without decoding cameras.
        expected = {p['name'] for p in parsed.get('pages', [])}
        missing = expected - {p['name'] for p in pages}
        if missing:
            print('[OpenSKP Cameras] Pages without a captured/decodable camera: '+', '.join(sorted(missing)))
        return pages
    return parsed.get('pages', [])


def camera_matrix(eye, target, up):
    eye=Vector(eye)*.0254; forward=Vector(target)*.0254-eye
    if forward.length < 1e-9: raise ValueError('Camera eye equals target')
    forward.normalize(); right=forward.cross(Vector(up))
    if right.length < 1e-9: raise ValueError('Camera up is parallel to view')
    right.normalize(); corrected=right.cross(forward).normalized()
    return Matrix(((right.x,corrected.x,-forward.x,eye.x),
                   (right.y,corrected.y,-forward.y,eye.y),
                   (right.z,corrected.z,-forward.z,eye.z),(0,0,0,1)))


def import_cameras(filepath, parsed, context, root):
    pages=pages_from_file(filepath, parsed)
    collection=None; created=[]
    for index,page in enumerate(pages):
        if page.get('eye') is None or page.get('target') is None: continue
        name=page.get('name') or 'Scene '+str(index+1)
        matrix=camera_matrix(page['eye'],page['target'],page.get('up') or (0,0,1))
        aspect=float(page.get('aspect_ratio') or 16/9)
        if not math.isfinite(aspect) or aspect<=0: raise ValueError('Invalid camera aspect ratio')
        if collection is None:
            collection=bpy.data.collections.new('SketchUp Scene Cameras');root.children.link(collection)
        data=bpy.data.cameras.new(name+'_Camera');obj=bpy.data.objects.new(name+'_Camera',data);collection.objects.link(obj)
        obj.matrix_world=matrix;data.sensor_width=36;data.sensor_height=max(36/aspect,1)
        clipping=page.get('clip')
        # Treat the observed legacy 1/1000 pair as a default, not a useful
        # 25.4m far plane: the tested saved view has geometry beyond it.
        if clipping is None or tuple(clipping)==(1.,1000.):
            data.clip_start=.1;data.clip_end=1000.
        else:
            data.clip_start=max(float(clipping[0])*.0254,1e-6)
            data.clip_end=max(float(clipping[1])*.0254,data.clip_start+1e-6)
        if page.get('parallel'):
            data.type='ORTHO';data.sensor_fit='AUTO';data.ortho_scale=max(1,aspect)*max(float(page.get('ortho_height',1)),1e-6)*.0254
        else:
            data.type='PERSP';data.sensor_fit='VERTICAL'
            fov=float(page.get('fov',35));data.lens=max(data.sensor_height/(2*math.tan(math.radians(fov)/2)),1)
        obj['openskp_scene_name']=name;obj['openskp_scene_index']=index
        obj['openskp_scene_target_distance']=(Vector(page['target'])-Vector(page['eye'])).length*.0254
        created.append(obj)
    if created: context.scene.camera=created[0]
    return len(created)
