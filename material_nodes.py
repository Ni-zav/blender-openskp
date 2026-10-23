"""Editable, self-contained material controls for OpenSKP imports."""
import bpy

GROUP_VERSION = 1


def _adjustment_group():
    for group in bpy.data.node_groups:
        if group.bl_idname == 'ShaderNodeTree' and group.get('openskp_adjustment_version') == GROUP_VERSION:
            return group
    group = bpy.data.node_groups.new('OpenSKP Material Adjustment', 'ShaderNodeTree')
    group['openskp_adjustment_version'] = GROUP_VERSION
    inputs = [
        ('Base Color', 'NodeSocketColor', (0.8, 0.8, 0.8, 1)),
        ('Tint', 'NodeSocketColor', (1, 1, 1, 1)),
        ('Hue', 'NodeSocketFloat', .5),
        ('Saturation', 'NodeSocketFloat', 1.),
        ('Brightness', 'NodeSocketFloat', 1.),
        ('Roughness', 'NodeSocketFloat', .8),
        ('Metallic', 'NodeSocketFloat', 0.),
        ('Alpha', 'NodeSocketFloat', 1.),
        ('Normal', 'NodeSocketVector', (0, 0, 0)),
    ]
    for name, socket_type, default in inputs:
        socket = group.interface.new_socket(name=name, in_out='INPUT', socket_type=socket_type)
        socket.default_value = default
        if socket_type == 'NodeSocketFloat':
            socket.min_value = 0
            socket.max_value = 2 if name in ('Saturation', 'Brightness') else 1
    for name, socket_type in [('Base Color', 'NodeSocketColor'), ('Roughness', 'NodeSocketFloat'),
                              ('Metallic', 'NodeSocketFloat'), ('Alpha', 'NodeSocketFloat'),
                              ('Normal', 'NodeSocketVector')]:
        group.interface.new_socket(name=name, in_out='OUTPUT', socket_type=socket_type)
    nodes, links = group.nodes, group.links
    source = nodes.new('NodeGroupInput'); source.location = (-500, 0)
    output = nodes.new('NodeGroupOutput'); output.location = (250, 0)
    hue = nodes.new('ShaderNodeHueSaturation'); hue.location = (-280, 100)
    tint = nodes.new('ShaderNodeMixRGB'); tint.blend_type = 'MULTIPLY'; tint.inputs[0].default_value = 1
    tint.location = (-40, 100); tint.label = 'Paint tint'
    for external, internal in [('Base Color', 'Color'), ('Hue', 'Hue'), ('Saturation', 'Saturation'), ('Brightness', 'Value')]:
        links.new(source.outputs[external], hue.inputs[internal])
    links.new(hue.outputs['Color'], tint.inputs[1]); links.new(source.outputs['Tint'], tint.inputs[2])
    links.new(tint.outputs['Color'], output.inputs['Base Color'])
    for name in ('Roughness', 'Metallic', 'Alpha', 'Normal'):
        links.new(source.outputs[name], output.inputs[name])
    return group


def build_material_nodes(material, *, image, color, roughness=.8, metallic=0.):
    """Preserve imported paint while exposing normal Blender shader controls.

    SketchUp does not provide a PBR bump map: generated bump starts at zero.
    The packed paint image remains active for Solid / NEOS Albedo previews.
    """
    nodes, links = material.node_tree.nodes, material.node_tree.links
    nodes.clear()
    output = nodes.new('ShaderNodeOutputMaterial'); output.location = (520, 80)
    bsdf = nodes.new('ShaderNodeBsdfPrincipled'); bsdf.location = (160, 80); bsdf.width = 260
    bsdf.label = 'Surface'
    adjustment = nodes.new('ShaderNodeGroup'); adjustment.node_tree = _adjustment_group()
    adjustment.location = (-140, 80); adjustment.width = 240; adjustment.label = 'Material controls'
    adjustment.inputs['Base Color'].default_value = color
    adjustment.inputs['Alpha'].default_value = color[3]
    adjustment.inputs['Roughness'].default_value = roughness
    adjustment.inputs['Metallic'].default_value = metallic
    for name in ('Base Color', 'Roughness', 'Metallic', 'Alpha'):
        links.new(adjustment.outputs[name], bsdf.inputs[name])
    links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])
    if image is not None:
        coords = nodes.new('ShaderNodeTexCoord'); coords.location = (-1090, 80); coords.width = 180
        mapping = nodes.new('ShaderNodeMapping'); mapping.location = (-850, 80); mapping.width = 200
        mapping.label = 'Texture position / rotation / scale'
        texture = nodes.new('ShaderNodeTexImage'); texture.location = (-580, 80); texture.width = 260
        texture.image = image; texture.label = image.name
        links.new(coords.outputs['UV'], mapping.inputs['Vector'])
        links.new(mapping.outputs['Vector'], texture.inputs['Vector'])
        links.new(texture.outputs['Color'], adjustment.inputs['Base Color'])
        alpha = nodes.new('ShaderNodeMath'); alpha.operation = 'MULTIPLY'; alpha.label = 'Texture alpha × paint opacity'
        alpha.location = (-570, -300); alpha.inputs[1].default_value = color[3]
        links.new(texture.outputs['Alpha'], alpha.inputs[0]); links.new(alpha.outputs[0], adjustment.inputs['Alpha'])
        gray = nodes.new('ShaderNodeRGBToBW'); gray.location = (-570, -480); gray.label = 'Optional height from color'
        bump = nodes.new('ShaderNodeBump'); bump.location = (-280, -360); bump.width = 210
        bump.label = 'Optional bump (off by default)'
        bump.inputs['Strength'].default_value = 0
        bump.inputs['Distance'].default_value = .01
        links.new(texture.outputs['Color'], gray.inputs['Color'])
        links.new(gray.outputs['Val'], bump.inputs['Height'])
        links.new(bump.outputs['Normal'], adjustment.inputs['Normal'])
        links.new(adjustment.outputs['Normal'], bsdf.inputs['Normal'])
        nodes.active = texture
        material.surface_render_method = 'DITHERED'
    else:
        nodes.active = adjustment
    for node in nodes:
        node.select = False
    nodes.active.select = True


def _copy_surface(source, material, *, uv_map, y_offset):
    """Copy an imported side's editable graph, routing its own UV layer."""
    source_nodes = source.node_tree.nodes
    nodes, links = material.node_tree.nodes, material.node_tree.links
    copied = {}
    for original in source_nodes:
        if original.type == 'OUTPUT_MATERIAL':
            continue
        node = nodes.new(original.bl_idname)
        for attribute in ('node_tree', 'image', 'operation', 'blend_type', 'vector_type',
                          'interpolation', 'projection', 'extension', 'invert'):
            if hasattr(original, attribute):
                setattr(node, attribute, getattr(original, attribute))
        node.location = (original.location.x, original.location.y+y_offset)
        node.width, node.label = original.width, original.label
        for dst, src in zip(node.inputs, original.inputs):
            if hasattr(dst, 'default_value') and hasattr(src, 'default_value'):
                dst.default_value = src.default_value
        copied[original] = node
    for link in source.node_tree.links:
        if link.from_node in copied and link.to_node in copied:
            from_index = list(link.from_node.outputs).index(link.from_socket)
            to_index = list(link.to_node.inputs).index(link.to_socket)
            links.new(copied[link.from_node].outputs[from_index], copied[link.to_node].inputs[to_index])
    # Keep Mapping editable but give the back side its own per-corner UVs.
    for node in list(copied.values()):
        if node.type == 'TEX_COORD':
            for link in list(node.outputs['UV'].links):
                uv = nodes.new('ShaderNodeUVMap'); uv.uv_map = uv_map
                uv.location = node.location; uv.width = node.width
                links.new(uv.outputs['UV'], link.to_socket)
            nodes.remove(node)
    output = next(node for node in source_nodes if node.type == 'OUTPUT_MATERIAL')
    return copied[output.inputs['Surface'].links[0].from_node]


def build_two_sided_material(front, back):
    """One physical face; its two paints no longer compete in the depth buffer."""
    material = bpy.data.materials.new(front.name + ' | ' + back.name)
    material.use_nodes = True
    material.diffuse_color = front.diffuse_color
    material.use_backface_culling = False
    material.surface_render_method = 'DITHERED'
    material.node_tree.nodes.clear()
    front_shader = _copy_surface(front, material, uv_map='UVMap', y_offset=450)
    back_shader = _copy_surface(back, material, uv_map='UVMap_Back', y_offset=-650)
    nodes, links = material.node_tree.nodes, material.node_tree.links
    geometry = nodes.new('ShaderNodeNewGeometry'); geometry.location = (500,650)
    mix = nodes.new('ShaderNodeMixShader'); mix.location = (760,100); mix.label = 'Front / Back paint'
    output = nodes.new('ShaderNodeOutputMaterial'); output.location = (1000,100)
    links.new(geometry.outputs['Backfacing'],mix.inputs[0])
    links.new(front_shader.outputs['BSDF'],mix.inputs[1]); links.new(back_shader.outputs['BSDF'],mix.inputs[2])
    links.new(mix.outputs[0],output.inputs['Surface'])
    # Workbench can display one active image only; use the stored front paint.
    image = next((n for n in nodes if n.type == 'TEX_IMAGE' and n.location.y > -300),None)
    nodes.active = image or front_shader
    for node in nodes:
        node.select = False
    nodes.active.select = True
    return material
