import bpy
import bmesh
import pprint
import math
import mathutils

class EdgeLoopSorter:

    def __init__(self):
        self.bm = bmesh.from_edit_mesh(bpy.context.edit_object.data)

    def execute(self):
        unselected_edges = [i for i in self.bm.edges if not i.select]
        starting_vertex1 = self.bm.select_history[0]
        neighbouring_vertex1, edge1 = self.get_neighbouring_vertex(starting_vertex1, unselected_edges)
        starting_vertex2 = self.bm.select_history[1]
        neighbouring_vertex2, edge2 = self.get_neighbouring_vertex(starting_vertex2, unselected_edges)
        loop1 = self.get_sorted_edge_loop(starting_vertex1, edge1)
        loop2 = self.get_sorted_edge_loop(starting_vertex2, edge2)
        positions = self.get_wire_positions(loop1, loop2)
        krl = self.get_linear_krl(positions)
        return self.wrap_boilerplate_krl(krl)

    def get_linear_krl(self, positions):
        krl = ''
        for position in positions:
            krl += 'LIN {E6POS:' +\
                   'X {0}, Y {1}, Z {2}, A {3}, B {4}, C {5}, '.format(
                        position['x'], position['y'], position['z'],
                        position['a'], position['b'], position['c']
                    ) + 'E1 0, E2 0, E3 0, E4 0, E5 0, E6 0} C_DIS\n'
        return krl

    def wrap_boilerplate_krl(self, code):
        krl = """&ACCESS RVP
&REL 1
&PARAM TEMPLATE = C:\KRC\Roboter\Template\\vorgabe
&PARAM EDITMASK = *
DEF hello ( )
GLOBAL INTERRUPT DECL 3 WHEN $STOPMESS==TRUE DO IR_STOPM ( )
INTERRUPT ON 3
BAS (#INITMOV,0 )
$BWDSTART = FALSE
PDAT_ACT = {VEL 45,ACC 100,APO_DIST 50}
FDAT_ACT = {TOOL_NO 6,BASE_NO 6,IPO_FRAME #BASE}
BAS (#PTP_PARAMS,45)
$VEL.CP=0.5
$APO.CDIS=50
$ORI_TYPE=#VAR

"""
        krl += code + '\nEND'
        return krl

    def get_wire_positions(self, loop1, loop2):
        positions = [{'x': 0, 'y': 500, 'z': 500, 'A': mathutils.Vector((0, 0, 1)), 'a': 0, 'b': 0, 'c': 0}]
        for index, vertex in enumerate(loop1):
            vertex1 = vertex
            vertex2 = loop2[index]
            midpoint = (vertex1.co + vertex2.co) / 2
            y_axis = (vertex2.co - vertex1.co).normalized()
	    
            if (len(loop1) > index + 1):
                next_vertex1 = loop1[index + 1]
                next_vertex2 = loop2[index + 1]
                next_midpoint = (next_vertex1.co + next_vertex2.co) / 2
                # I don't think the midpoint approach works.
                # x_axis = (next_midpoint - midpoint).normalized()
                # z_axis = (y_axis.cross(x_axis)).normalized()
                x_axis = (y_axis.cross(vertex1.normal)).normalized()
                z_axis = (y_axis.cross(x_axis)).normalized()
            else:
                x_axis = (y_axis.cross(vertex1.normal)).normalized()
                z_axis = (y_axis.cross(x_axis)).normalized()

            # z axis is negative because ...
            # This represents a coplanar approach
            theta_x, theta_y, theta_z = self.get_intrinsic_rotations(x_axis, y_axis, - z_axis, positions)

            # This represents a normal approach
            #theta_x, theta_y, theta_z = self.get_intrinsic_rotations(z_axis, y_axis, x_axis, positions)

            positions.append({
                'x': -round(midpoint.z),
                'y': round(midpoint.y),
                'z': round(midpoint.x),
                'a': theta_x,
                'b': theta_y,
                'c': - theta_z # For some reason, the C angle does not obey the right hand screw rule
            })

        positions.pop(0)
        return positions

    def get_intrinsic_rotations(self, x_axis, y_axis, z_axis, positions):
        R11 = x_axis.x
        R12 = y_axis.x
        R13 = z_axis.x
        R21 = x_axis.y
        R22 = y_axis.y
        R23 = z_axis.y
        R33 = z_axis.z
        theta_y = round(math.degrees(math.atan2(R13, math.sqrt(math.pow(R11, 2) + math.pow(R12, 2)))))

        if abs(theta_y) != 90:
            theta_x = round(math.degrees(math.atan2(-R23, R33)))
            theta_z = round(math.degrees(math.atan2(-R12, R11)))
        else:
            coefficient = math.sin(math.radians(theta_y))
            previous_theta_z = positions[-1]['c']
            theta_x = round((math.degrees(math.atan2(R21, R22)) - previous_theta_z) / coefficient)
            theta_z = round(previous_theta_z)

        return theta_x, theta_y, theta_z

    def get_sorted_edge_loop(self, starting_vertex, starting_edge):
        self.bm.select_mode = {'EDGE'}
        for edge in self.bm.edges:
            edge.select = (edge == starting_edge)

        bpy.context.scene.objects.active = bpy.context.scene.objects.active
        bpy.ops.mesh.loop_multi_select()
        selected_edges = [i for i in self.bm.edges if i.select]
        return self.sort_edge_loop(starting_vertex, selected_edges)

    def sort_edge_loop(self, starting_vertex, edges):
        ordered_vertices = [starting_vertex]
        while len(edges) > 0:
            neighbouring_vertex, neighbouring_edge = self.get_neighbouring_vertex(ordered_vertices[-1], edges)
            ordered_vertices.append(neighbouring_vertex)
            edges.remove(neighbouring_edge)
        return ordered_vertices

    def get_neighbouring_vertex(self, vertex, edges):
        for edge in edges:
            if edge.verts[0] == vertex:
                return (edge.verts[1], edge)
            elif edge.verts[1] == vertex:
                return (edge.verts[0], edge)

edge_loop_sorter = EdgeLoopSorter()
code = edge_loop_sorter.execute()
output_file = open('output.src', 'w')
output_file.write(code)
output_file.close()
