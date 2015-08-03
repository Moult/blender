import os
import bpy
import bmesh
import pprint
import math
import mathutils
import subprocess

class FiniteElementMesher:

    def __init__(self):
        self.youngs_modulus = 13990000000.0
        self.poissons_ratio = 0.29
        self.density = 2397.0
        self.pressure_overclosure = self.youngs_modulus * 10
        self.friction_coefficient = 0.48
        self.stick_slope = self.youngs_modulus / 10 # Arbitrary nonsense?
        self.gravity = 9.81

        self.node_index = 1
        self.element_index = 1
        self.object_node_offset = 0

        self.surfaces = {
            'S1': [1, 2, 3],
            'S2': [1, 4, 2],
            'S3': [2, 4, 3],
            'S4': [3, 4, 1]
            }

        self.base_path = 'C:/Users/dmou8237/Desktop/featest/'
        self.tetgen_path = 'C:/Users/dmou8237/Desktop/featest/tetgen.exe'
        self.stl_path = self.base_path + 'fea.stl'
        self.node_path = self.base_path + 'fea.1.node'
        self.element_path = self.base_path + 'fea.1.ele'
        self.inp_path = self.base_path + 'fea.inp'
        self.bash_path = 'C:/cygwin64/bin/bash'
        self.reformat_path = self.base_path + 'reformat.sh'
        os.chdir(self.base_path)

        open(self.inp_path, 'w').close()
        self.inp_file = open(self.inp_path, 'a')

        self.nodes = []
        self.elements = []
        self.slaves = []
        self.masters = []

    def execute(self):
        fea_objects = []

        objects = bpy.data.objects
        for object in objects:
            self.triangulate(object)
            self.save_ascii_stl(object)
            self.generate_delaunay_tetrahedralization()
            fea_objects.append({
                'object': object,
                'is_master': object['master'] == 1,
                'nodes': self.get_nodes(),
                'elements': self.get_elements()
                })
            object.select = False

        for object in fea_objects:
            self.nodes.extend(object['nodes'])
            self.elements.extend(object['elements'])
            if object['is_master']:
                print('MASTER DETECT');
                self.masters.extend(self.get_tagged_surfaces(object))
            else:
                print('SLAVE DETECT');
                self.slaves.extend(self.get_tagged_surfaces(object))

        self.convert_m_to_mm()
        self.write_inp_heading()
        self.write_inp_node()
        self.write_inp_element()
        self.write_inp_ground_boundary(self.detect_ground_nodes())
        self.write_inp_material()
        self.write_inp_contact_pair()
        self.write_inp_step()
        self.inp_file.close()

    def triangulate(self, object):
        bpy.context.scene.objects.active = object
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.quads_convert_to_tris()
        bpy.ops.object.mode_set(mode='OBJECT')

    def save_ascii_stl(self, object):
        object.select = True
        bpy.ops.export_mesh.stl(filepath=self.stl_path, axis_forward='Y', axis_up='Z', ascii=True)

    def generate_delaunay_tetrahedralization(self):
        #subprocess.call([self.tetgen_path, '-q', '-p', '-g', '-F', '-o2', self.stl_path])
        subprocess.call([self.tetgen_path, '-p', '-g', '-F', '-o2', self.stl_path])
        # Potential discrepancies between our triangulation and theirs when -q argument used

    def get_nodes(self):
        nodes = self.load_tetgen_output(self.node_path, 2)
        for index, node in enumerate(nodes):
            nodes[index][0] = self.node_index
            self.node_index = self.node_index + 1
        return nodes

    def get_elements(self):
        unsorted_elements = self.load_tetgen_output(self.element_path)
        elements = []
        for element in unsorted_elements:
            elements.append([
                self.element_index,
                element[1] + self.object_node_offset,
                element[2] + self.object_node_offset,
                element[3] + self.object_node_offset,
                element[4] + self.object_node_offset,
                element[7] + self.object_node_offset,
                element[8] + self.object_node_offset,
                element[10] + self.object_node_offset,
                element[6] + self.object_node_offset,
                element[9] + self.object_node_offset,
                element[5] + self.object_node_offset
                ])
            self.element_index = self.element_index + 1
        self.object_node_offset = self.node_index - 1
        return elements

    def get_vertices_in_vertex_group(self, object):
        vertices = []
        for vertex in object['object'].data.vertices:
            if (len(vertex.groups)):
                vertices.append(
                    [round(vertex.co.x, 2), round(vertex.co.y, 2), round(vertex.co.z, 2)]
                )
        return vertices

    def get_faces_in_vertex_group(self, object):
        print('getting faces in vertex group')
        faces = []
        for polygon in object['object'].data.polygons:
            vertex1 = object['object'].data.vertices[polygon.vertices[0]]
            vertex2 = object['object'].data.vertices[polygon.vertices[1]]
            vertex3 = object['object'].data.vertices[polygon.vertices[2]]

            if not (len(vertex1.groups) and len(vertex2.groups) and len(vertex3.groups)):
                continue

            pprint.pprint(polygon)
            faces.append([
                [round(vertex1.co.x, 2), round(vertex1.co.y, 2), round(vertex1.co.z, 2)],
                [round(vertex2.co.x, 2), round(vertex2.co.y, 2), round(vertex2.co.z, 2)],
                [round(vertex3.co.x, 2), round(vertex3.co.y, 2), round(vertex3.co.z, 2)]
            ])
        return faces

    def is_node_in_tri_old(self, node, tri1, tri2, tri3):
        check = mathutils.geometry.intersect_point_tri(
            mathutils.Vector(node),
            mathutils.Vector(tri1),
            mathutils.Vector(tri2),
            mathutils.Vector(tri3)
            )
        if check is not None and check == mathutils.Vector(node):
            return True
        return False

    def is_node_in_tri(self, node, tri1, tri2, tri3):
        if str(node) == str(tri1) or str(node) == str(tri2) or str(node) == str(tri3):
            return True
        return False

    def get_tagged_surfaces(self, object):
        faces = []
        print('get tagged verts')
        tagged_vertices = self.get_vertices_in_vertex_group(object)
        print(tagged_vertices)
        print('finished getting tagged verts')
        #original_faces = self.get_faces_in_vertex_group(object)

        #for original_face in original_faces:
        #    print('TESTING ' + str(original_face[0]) + ',' + str(original_face[1]) + ',' + str(original_face[2]))

        for element in object['elements']:
            # Test each combination of surfaces
            for surface_name, surface_indices in self.surfaces.items():
                node1_index = element[surface_indices[0]]
                node2_index = element[surface_indices[1]]
                node3_index = element[surface_indices[2]]

                for node in object['nodes']:
                    if node[0] == node1_index:
                        node1 = [node[1], node[2], node[3]]
                    elif node[0] == node2_index:
                        node2 = [node[1], node[2], node[3]]
                    elif node[0] == node3_index:
                        node3 = [node[1], node[2], node[3]]

                if node1 in tagged_vertices and node2 in tagged_vertices and node3 in tagged_vertices:
                    print('WE GOT ONE')
                    faces.append([element[0], surface_name])

                """
                for original_face in original_faces:
                    check_node1 = self.is_node_in_tri(node1, original_face[0], original_face[1], original_face[2])
                    check_node2 = self.is_node_in_tri(node2, original_face[0], original_face[1], original_face[2])
                    check_node3 = self.is_node_in_tri(node3, original_face[0], original_face[1], original_face[2])
                    #if check_node1:
                        #print('RESULT FOR ' + str(surface_name) + ', WITH ' + str(node1) + ',' + str(original_face[0]) + ',' + str(original_face[1]) + ',' + str(original_face[2]) + ' IS ' + str(check_node1))

                if node1_index == 40 and node2_index == 43 and node3_index == 34:
                    print('HERE IT IS')
                    print(node1_index, node2_index, node3_index)
                    print(node1, node2, node3)
                    print('a' == 'a')
                    print(node3)
                    print(original_face[2])
                    print(node3 == original_face[2])
                    print(check_node1, check_node2, check_node3)


                if check_node1 and check_node2:
                    print('NODECHECKA ' + str(node1) + ',' + str(node2) + ',' + str(node3))

                if check_node1 and check_node2 and check_node3:
                    print('WE GOT ONE')
                    faces.append([element[0], surface_name])
                """

        return faces

    def convert_m_to_mm(self):
        return
        self.youngs_modulus = 13990.0
        self.density = 0.000002397
        self.pressure_overclosure = self.youngs_modulus * 10
        self.stick_slope = self.youngs_modulus / 10 # Arbitrary nonsense?
        self.gravity = 9810.0

        for index, node in enumerate(self.nodes):
            self.nodes[index][1] = node[1] * 1000
            self.nodes[index][2] = node[2] * 1000
            self.nodes[index][3] = node[3] * 1000

    def write_inp_heading(self):
        print('*HEADING\nGenerated FEA model, mm, kg, N, s\n', file=self.inp_file)

    def write_inp_node(self):
        print('\n*NODE, NSET=Nall', file=self.inp_file)
        for node in self.nodes:
            print('{0}, {1}, {2}, {3}'.format(*node), file=self.inp_file)

    def write_inp_element(self):
        print('\n*ELEMENT, TYPE=C3D10, ELSET=Eall', file=self.inp_file)
        for element in self.elements:
            print('{0}, {1}, {2}, {3}, {4}, {5}, {6}, {7}, {8}, {9}, {10}'.format(*element), file=self.inp_file)
            # I may have made a bad assumption here. This only applies to "simple" meshes
            # If this is true, good luck future Dion.

    def detect_ground_nodes(self):
        ground_nodes = []
        for node in self.nodes:
            if node[3] == 0:
                ground_nodes.append(node[0])
        return ground_nodes

    def write_inp_ground_boundary(self, ground_nodes):
        if len(ground_nodes):
            print('\n*NSET, NSET=FIX', file=self.inp_file)
            print(',\n'.join(str(node) for node in ground_nodes), file=self.inp_file)
            print('\n*BOUNDARY', file=self.inp_file)
            print('FIX, 1', file=self.inp_file)
            print('FIX, 2', file=self.inp_file)
            print('FIX, 3', file=self.inp_file)

    def write_inp_material(self):
        print('\n*MATERIAL, NAME=SANDSTONE', file=self.inp_file)
        print('*ELASTIC', file=self.inp_file)
        print(self.youngs_modulus, ', ', self.poissons_ratio, file=self.inp_file)
        print('*DENSITY', file=self.inp_file)
        print(self.density, file=self.inp_file)
        print('*SOLID SECTION, ELSET=Eall, MATERIAL=SANDSTONE', file=self.inp_file)

    def write_inp_contact_pair(self):
        print('\n*SURFACE, NAME=Sslav', file=self.inp_file)
        for slave in self.slaves:
            print('{0},{1}'.format(*slave), file=self.inp_file)
        print('*SURFACE, NAME=Smast', file=self.inp_file)
        for master in self.masters:
            print('{0},{1}'.format(*master), file=self.inp_file)
        print('*CONTACT PAIR, INTERACTION=SI1, TYPE=SURFACE TO SURFACE', file=self.inp_file)
        print('Sslav, Smast', file=self.inp_file)
        print('*SURFACE INTERACTION,NAME=SI1', file=self.inp_file)
        print('*SURFACE BEHAVIOR,PRESSURE-OVERCLOSURE=LINEAR', file=self.inp_file)
        print(self.pressure_overclosure, ',3', file=self.inp_file)
        print('*FRICTION', file=self.inp_file)
        print(self.friction_coefficient, ',', self.stick_slope, file=self.inp_file)

    def write_inp_step(self):
        print('\n*STEP,NLGEOM', file=self.inp_file)
        print('*DYNAMIC', file=self.inp_file)
        print('0.01,0.5', file=self.inp_file)
        print('*DLOAD', file=self.inp_file)
        print('Eall,GRAV,', self.gravity, ',0.,0.,-1.', file=self.inp_file)
        print('*NODE FILE', file=self.inp_file)
        print('U', file=self.inp_file)
        print('*EL FILE', file=self.inp_file)
        print('S', file=self.inp_file)
        print('*END STEP', file=self.inp_file)


    def load_tetgen_output(self, source, rounding = None):
        with open(source) as file:
            lines = [line.rstrip('\n') for line in file]
            lines.pop(0)
            lines.pop(-1)
            for index, line in enumerate(lines):
                lines[index] = line.split()
                for index2, value in enumerate(lines[index]):
                    if rounding:
                        lines[index][index2] = round(float(value), rounding)
                    else:
                        lines[index][index2] = round(float(value))
            return lines

print('===== STARTING EXECUTION =====')
finite_element_mesher = FiniteElementMesher()
finite_element_mesher.execute()
# output_file = open('output.src', 'w')
# output_file.write(code)
# output_file.close()
