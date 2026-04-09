from django.test import TestCase
from grids.parsing.grid_parser import _extract_student_names, _extract_curriculum_blocks_data

class GridParserTests(TestCase):
    def test_extract_student_names_with_space_before_colon(self):
        # Issue 1: "Record of : " vs "Record of:"
        synthetic_block = """
Student Number: 12345678
Record of : Special Ed
Admit Term: 2020/2021 Semester I
        """
        names = _extract_student_names(synthetic_block)
        self.assertEqual(len(names), 1)
        self.assertEqual(names[0], "Special Ed")

        # Standard case, without space
        synthetic_block_standard = """
Student Number: 12345678
Record of: Normal Name Guy
Admit Term: 2020/2021 Semester I
        """
        names_std = _extract_student_names(synthetic_block_standard)
        self.assertEqual(len(names_std), 1)
        self.assertEqual(names_std[0], "Normal Name Guy")

    def test_extract_curriculum_blocks_handle_undeclared_degree(self):
        # Issue 2: Degree: Undeclared bleeding into subsequent fields
        synthetic_curriculum = """
CURRENT CURRICULUM
CURRENT PROGRAMME
Admit Term: 2022/2023 Summer
Programme Level: Undergraduate
Degree: Undeclared
Programme: Summer Program-All Faculties
Faculty: No College Designated
Campus: St Augustine
Department: Undeclared
Major: Undeclared
Degree GPA: 2.88
        """
        # _extract_curriculum_blocks_data returns a list of dictionaries
        blocks = _extract_curriculum_blocks_data(synthetic_curriculum)
        
        self.assertEqual(len(blocks), 1)
        block = blocks[0]
        
        # Ensure that 'programme' didn't incorrectly grab 'College' or 'Campus' because of an offset
        self.assertEqual(block.get("programme"), "Summer Program-All Faculties")
        self.assertEqual(block.get("degree"), "Undeclared")
        self.assertEqual(block.get("faculty"), "No College Designated")
        self.assertEqual(block.get("campus"), "St Augustine")
        self.assertEqual(block.get("major"), "Undeclared")
