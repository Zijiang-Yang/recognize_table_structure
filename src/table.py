import itertools
import pandas as pd
import xml.etree.ElementTree as ET
from typing import Union
from utils.chain import get_chain
from utils.parse_xml import parse_xml_output, parse_xml_output_without_thinking
from utils.classifications_explanation import get_classifications_explanation
from utils.custom_chat_openai import input_data
import os
import pdb
import json

table_structure_chain = get_chain("table_structure_recognize")
table_structure_no_mt_chain = get_chain("table_structure_recognize_no_main_title")
match_key_chain = get_chain("match_key")
match_key_multi_class_chain = get_chain("match_key_multi_class")
get_enum_from_maintitle_chain = get_chain("get_enum_from_maintitle")
classifications, classification_explained = get_classifications_explanation()

#Cell类保存每个单元格信息
class Cell:
    def __init__(self, row_index, column_index, value, merge_range=None):
        self.row_index = row_index
        self.column_index = column_index
        self.value = value
        self.merge_range = merge_range if merge_range else []
        self.is_num = self._is_num(value)
    
    def _is_num(self, value):
        if value is None:
            return False
        if isinstance(value, int) or isinstance(value, float):
            return True
        try:
            float(value)
            return True
        except ValueError:
            return False

#CellPool是Row和Column的基类
class CellPool:
    def __init__(self, index):
        self.index = index
        self.cell_list = []
        self.index_2_cell_value = {}
        self.total_count = 0
        self.total_num_count = 0
        self.is_pivot = False
        self.pivot_enum = []
        self.pivot_enum_2_index = {}
        self.pivot_index_2_enum = {}
        self.structure = {}

    def insert(self, cell:Cell):
        self.cell_list.append(cell)
        self.index_2_cell_value[str(self._get_index(cell))] = str(cell.value) if cell.value is not None else None
        self.total_count += 1
        self.total_num_count += 1 if cell.is_num else 0

    #一行/列中数字的占比
    def get_statistics(self):
        self.num_percent = self.total_num_count / self.total_count if self.total_count != 0 else 0

    def _get_index(self, cell):
        # This method should be overridden in subclasses
        raise NotImplementedError("This method should be overridden in subclasses")
    
    #将一行/列的内容拼接
    def output_content_str(self, skip_list:list=None):
        if skip_list is not None:
            skip_set = set(skip_list)
        else:
            skip_set = set()
        contents = []
        for index, cell_value in self.index_2_cell_value.items():
            if int(index) > 200:
                break
            if cell_value is None:
                continue
            label = self.structure.get(index)
            if label in skip_set:
                continue
            contents.append(cell_value)
        # row_list = [f'<Cell><Data ss:Type="String">{content}</Data></Cell>' for content in contents]
        # row_content = '\t<Row>\n\t\t' + "\n\t\t".join(row_list) + '\n\t</Row>'
        return "|".join(contents)
        # return row_content
    
    def output_unique_content_str(self):
        raise NotImplementedError("This method should be overridden in subclasses")

    def update_structure(self, table_structure:dict):
        self.structure = table_structure
    
    def update_pivot_enum(self):
        raise NotImplementedError("This method should be overridden in subclasses")
    
    #将字段及相应可选选项更新
    def update_pivot_enum(self):
        if not self.is_pivot:
            return
        for index, structure_label in self.structure.items():
            if structure_label != "content":
                continue
            cell_value = self.index_2_cell_value.get(index)
            if cell_value is None:
                continue
            if cell_value not in self.pivot_enum:
                self.pivot_enum.append(cell_value)
            if cell_value not in self.pivot_enum_2_index:
                self.pivot_enum_2_index[cell_value] = []
            if index not in self.pivot_enum_2_index[cell_value]:
                self.pivot_enum_2_index[cell_value].append(index)
            if index not in self.pivot_index_2_enum:
                self.pivot_index_2_enum[index] = cell_value


class Row(CellPool):
    def __init__(self, row_index):
        super().__init__(row_index)
        self.merged_range = None
        self.is_all_merged = None
        self.is_all_merged_content = None

    def _get_index(self, cell):
        return cell.column_index
    
    def insert(self, cell):
        super().insert(cell)
        #防止出现第一个单元格为不合并，其他为合并的情况
        if self.is_all_merged == False:
            return
        if cell.merge_range:
            if self.merged_range is None:
                self.merged_range = cell.merge_range
                self.is_all_merged = True
            else:
                if self.merged_range != cell.merge_range:
                    self.is_all_merged = False
        else:
            self.is_all_merged = False
        
    def get_statistics(self):
        super().get_statistics()
        if self.is_all_merged:
            self.is_all_merged_content = str(self.cell_list[0].value) if len(self.cell_list) > 0 else ""
     
    #将带有最后一个row_title的content拼接
    def output_unique_content_str_with_rowtitle(self):
        contents = []
        for index, label in self.structure.items():
            cell_value = self.index_2_cell_value.get(index)
            print(cell_value)
            if label == "row_title":
                if str(int(index)+1) in self.structure.keys() and self.structure[str(int(index)+1)] == "content":
                    contents.append(cell_value)
                else:
                    continue
            if cell_value is None:
                continue
            if cell_value not in contents:
                contents.append(cell_value)
        print('ccccccccccccccccc',contents)
        if contents and all(content for content in contents):
            return ",".join(contents)
        else:
            return '其他'
    
    #将不带row_title的content拼接
    def output_unique_content_str_without_rowtitle(self):
        contents = []
        for index, label in self.structure.items():
            cell_value = self.index_2_cell_value.get(index)
            #print(cell_value)
            if label == "row_title":
                continue
            if cell_value is None:
                continue
            if cell_value not in contents:
                contents.append(cell_value)
        if contents:
            return ",".join(contents)
        else:
            return '其他'


class Column(CellPool):
    def __init__(self, column_index):
        super().__init__(column_index)
        self.row_title_list = []
        self.row_title = None

    @staticmethod
    def index_to_letter(index):
        # 将1变为A, 2变为B, 以此类推
        string = ""
        while index > 0:
            index, remainder = divmod(index - 1, 26)
            string = chr(65 + remainder) + string
        return string

    def _get_index(self, cell):
        return cell.row_index
    
    def update_row_title(self):
        if not self.structure:
            return
        for index, label in self.structure.items():
            if label == "row_title":
                cell_value = self.index_2_cell_value.get(index)
                if cell_value is None:
                    continue
                if cell_value not in self.row_title_list:
                    self.row_title_list.append(cell_value)
        self.row_title = "_".join(self.row_title_list)
    
    def output_unique_content_str(self):
        if not self.structure:
            return
        print('+++++++++++++++++++++',self.row_title_list)
        contents = [self.row_title_list[-1] if len(self.row_title_list) > 0 else ""]
        #print(self.structure)
        for index, label in self.structure.items():
            if label in {"main_title", "row_title"}:
                continue
            cell_value = self.index_2_cell_value.get(index)
            if cell_value is None:
                continue
            if cell_value not in contents:
                contents.append(cell_value)
        print(contents)
        if contents == ['']:
            return '其他'
        else:
            num = min(len(contents),10)
            return ",".join(contents[:num])
    
#Field类用于储存一行/列中包含的因子和对应选项
class Field:
    def __init__(self, field_type, match_key, cell_pool:Union[Row, Column] = None):
        self._field_type = None
        self.field_type = field_type
        self.match_key = match_key
        self.cell_pool = cell_pool
        if self.field_type in {"row", "column"}:
            self.parse_cell_pool()

    @property
    def field_type(self):
        return self._field_type

    @field_type.setter
    def field_type(self, value):
        if value not in {"row", "column", "main_title"}:
            raise ValueError("field_type must be 'row', 'column', or 'main_title'")
        self._field_type = value

    def parse_cell_pool(self):
        self.index = self.cell_pool.index
        self.enum = self.cell_pool.pivot_enum
        self.enum_2_index = self.cell_pool.pivot_enum_2_index
        self.index_2_enum = self.cell_pool.pivot_index_2_enum
        #print(f"============> enum: {self.enum}")
        #print(f"============> index_2_enum: {self.index_2_enum}")

class Table:
    def __init__(self, sheet_name):
        self.sheet_name = sheet_name
        self.cell_coordinate_2_value = {}
        self.columns = {}
        self.rows = {}
        self.table_structure_by_row = {}
        self.table_structure_by_column = {}
        self.field_by_type = {"row": [], "column": [], "main_title": []}
        self.content_table_range = [-1, -1, -1, -1] #first_row, last_row, first_column, last_column
    
    def load_table(self, worksheet):
        for row in worksheet.iter_rows():
            for cell in row:
                merge_range = None
                if cell.coordinate in worksheet.merged_cells:
                    for range in worksheet.merged_cells.ranges:
                        if cell.coordinate in range:
                            merge_range = [range.min_row, range.min_col, range.max_row, range.max_col]
                            value = worksheet.cell(row=range.min_row, column=range.min_col).value
                            break
                else:
                    value = cell.value

                self.cell_coordinate_2_value[cell.coordinate] = value
                new_cell = Cell(cell.row, cell.column, value, merge_range)

                if str(cell.column) not in self.columns:
                    self.columns[str(cell.column)] = Column(cell.column)
                self.columns[str(cell.column)].insert(new_cell)

                if str(cell.row) not in self.rows:
                    self.rows[str(cell.row)] = Row(cell.row)
                self.rows[str(cell.row)].insert(new_cell)

        for _, column in self.columns.items():
            column.get_statistics()
        
        for _, row in self.rows.items():
            row.get_statistics()


    #取前20行，后10行
    def _convert_table_2_str(self, recognize_type:str):
        if recognize_type == "row":
            cell_pool = self.rows
            skip_list = None
        else:
            cell_pool = self.columns
            skip_list = ["main_title", "additional_information"]
        contents = []
        row_count = len(cell_pool.keys())
        if row_count > 30:
            start_range = [f'{i}' for i in range(1,21)]
            end_range = [f'{i}' for i in range(row_count-10,row_count+1)]
            for row_index, row in cell_pool.items():
                if row_index not in start_range and row_index not in end_range:
                    continue
                contents.append(f"第{row_index}行内容：")
                contents.append(row.output_content_str(skip_list))
        else:
            for row_index, row in cell_pool.items():
                contents.append(f"第{row_index}行内容：")
                contents.append(row.output_content_str(skip_list))
        # contents_xml = '<Table>\n' + '\n'.join(contents) +'\n</Table>'
        # return contents_xml
        return "\n".join(contents)

    def _get_parsed_res(self, row_recognize_res, recognize_type:str):
        root = ET.fromstring(row_recognize_res)
        table_structure = {}
        if recognize_type == "row":
            row_count = len(self.rows.keys())
        else:
            row_count = len(self.columns.keys())
        if row_count > 30:
            start_part = [f'{i}' for i in range(1,21)]
            middle_part = [f'{i}' for i in range(21,row_count-10)]
            end_part = [f'{i}' for i in range(row_count-10,row_count+1)]
            for row in root.findall('row'):
                index = row.get('index')
                if index not in start_part:
                    break
                category = row.get('category')
                table_structure[index] = category
            for index in middle_part:
                table_structure[index] = 'content'
            for row in root.findall('row'):
                index = row.get('index')
                if index in end_part:
                    category = row.get('category')
                    table_structure[index] = category
        else:
            for row in root.findall('row'):
                index = row.get('index')
                category = row.get('category')
                table_structure[index] = category
        return table_structure

    #后处理main_title
    def _post_process_main_title(self, table_structure:dict):
        """如果整行都为合并单元格，修改为main_title"""
        for index, label in table_structure.items():
            if label == "additional_information":
                continue
            row = self.rows.get(index)
            if row is None or not row.is_all_merged:
                continue
            table_structure[index] = "main_title"
        for index, label in table_structure.items():
            if label == "row_title":
                break
            table_structure[index] = "main_title"
        first_index = -1
        last_index = -1
        row_type = "main_title"
        type_list = [table_structure[index] for index in table_structure]
        for i in range(len(type_list)):
            if type_list[i] == row_type:
                last_index = i
                if first_index < 0:
                    first_index = i
        if first_index >= 0:
            check = all(element == row_type for element in type_list[first_index:last_index+1])
            if check:
                return table_structure
            if first_index >= 0 and last_index >= 0:
                table_structure.update({f'{i}': "main_title" for i in range(first_index+1, last_index + 2)})
        return table_structure

    #后处理row_title
    def _post_process_row_title(self, table_structure:dict):
        '''
        大模型识别效果有可能不准，会出现row_title中间夹杂content的情况
        先把最后一个main_title到第一个row_title之间的都赋成row_title
        再把第一个row_title到最后一个row_title之间的都赋成row_title
        '''
        row_type = "row_title"
        type_list = [table_structure[index] for index in table_structure]
        if row_type not in type_list:
            return table_structure
        for index, label in table_structure.items():
            if label == "row_title":
                break
            elif label == "main_title":
                continue
            #print('*******************',index,label)
            table_structure[index] = "row_title"
        first_index = -1
        last_index = -1
        for i in range(len(type_list)):
            if type_list[i] == row_type:
                last_index = i
                if first_index < 0:
                    first_index = i
        check = all(element == row_type for element in type_list[first_index:last_index+1])
        if check:
            return table_structure
        if first_index >= 0 and last_index >= 0:
            table_structure.update({f'{i}': "row_title" for i in range(first_index+1, last_index + 2)})
        return table_structure

    def _post_process_parsed_res(self, table_structure:dict, recognize_type:str):
        if recognize_type == "row":
            table_structure = self._post_process_main_title(table_structure)
        table_structure = self._post_process_row_title(table_structure)
        return table_structure

    def parse_recognize_res(self, recognize_res:str, recognize_type:str):
        parse_recognize_res = '<rows>' + parse_xml_output_without_thinking(recognize_res,['rows'])['rows'][0] + '</rows>'
        table_structure = self._get_parsed_res(parse_recognize_res, recognize_type)
        table_structure = self._post_process_parsed_res(table_structure, recognize_type)
        return table_structure

    #用table_structure更新表格结构columns, rows
    def update_structure(self, table_structure:dict, update_type:str):
        if update_type == "row":
            cell_pools = self.columns
        else:
            cell_pools = self.rows

        for _, cell_pool in cell_pools.items():
            cell_pool.update_structure(table_structure)

    #用table_structure更新表格结构pivot_cell, pivot_enum
    def update_structure_enum(self, table_structure:dict, update_type:str):
        if update_type == "row":
            pivot_cell_pools = self.rows
        else:
            pivot_cell_pools = self.columns
        for index, structure_label in table_structure.items():
            if structure_label in {"row_title"}:
                pivot_cell_pools[index].is_pivot = True
                pivot_cell_pools[index].update_pivot_enum()

    #大模型识别表格结构
    def recognize(self, recognize_type:str):
        spreadsheet_info = self._convert_table_2_str(recognize_type)
        if recognize_type == "row":
            chain = table_structure_chain
        else:
            chain = table_structure_no_mt_chain
        input_data.info = spreadsheet_info
        recognize_res = chain.invoke({
            "spreadsheet_info": spreadsheet_info
        })
        print(f"============>spreadsheet_info: {spreadsheet_info}")
        print(f"============>recognize_res: {recognize_res}")
        return recognize_res

    #更新表格content范围
    def update_content_table_range(self):
        first_row = -1
        last_row = -1
        first_column = -1
        last_column = -1
        row_structure = self.table_structure_by_row
        row_type_list = [row_structure[index] for index in self.table_structure_by_row]
        for i in range(len(row_type_list)):
            if row_type_list[i] == 'content':
                last_row = i+1
                if first_row < 0:
                    first_row = i+1
        column_structure = self.table_structure_by_column
        column_type_list = [column_structure[index] for index in self.table_structure_by_column]
        for i in range(len(column_type_list)):
            if column_type_list[i] == 'content':
                last_column = i+1
                if first_column < 0:
                    first_column = i+1
        self.content_table_range = [first_row, last_row, first_column, last_column]

    #识别表格结构
    def recognize_table_structure(self):
        #recognize_by_row
        recognize_type = "row"
        row_recognize_res = self.recognize(recognize_type)
        table_structure_by_row = self.parse_recognize_res(row_recognize_res, recognize_type)
        self.update_structure(table_structure_by_row, recognize_type)
        self.table_structure_by_row = table_structure_by_row
        # print(table_structure_by_row)
        #pdb.set_trace()

        #recognize_by_column
        recognize_type = "column"
        column_recogize_res = self.recognize(recognize_type)
        table_structure_by_column = self.parse_recognize_res(column_recogize_res, recognize_type)
        self.update_structure(table_structure_by_column, recognize_type)
        self.table_structure_by_column = table_structure_by_column

        self.update_structure_enum(table_structure_by_row, 'row')
        self.update_structure_enum(table_structure_by_column, 'column')
        self.update_content_table_range()
        

        for _, column in self.columns.items():
            column.update_row_title()

    def _post_process_match_key(self, match_key:str):
        if match_key == "其他":
            return 
        #TODO if match_key not in all_match_keys: return 
        match_key = match_key.strip()
        return match_key

    def parse_match_key_res(self, match_key_res):
        xml_res = parse_xml_output_without_thinking(match_key_res, tags=["result"], first_item_only=True)
        match_key = xml_res["result"]
        if match_key is None:
            return
        return match_key

    #匹配因子
    def match_keys(self):
        #by column 按列匹配
        for _, column in self.columns.items():
            if not column.is_pivot:
                continue
            current_info = column.output_unique_content_str()
            input_data.info = current_info
            match_key_res = match_key_chain.invoke({
                "current_info": current_info,
                'classification': classifications, 
                'classification_explained': classification_explained
            })
            print(f"============>current_info: {current_info}")
            print(f"============>match_key_res: {match_key_res}")
            match_key = self.parse_match_key_res(match_key_res)
            if match_key is None:
                continue
            match_key = self._post_process_match_key(match_key)
            if match_key is None:
                continue
            print(f"=======>match key: {match_key}")
            #创建Field类对象存储匹配的因子和相关可选项
            field = Field("column", match_key, column)
            self.field_by_type["column"].append(field)

        #by row 按行匹配
        for _, row in self.rows.items():
            if not row.is_pivot:
                continue
            current_info = row.output_unique_content_str_with_rowtitle()
            if not current_info:
                continue
            input_data.info = current_info
            match_key_res = match_key_chain.invoke({
                "current_info": current_info,
                'classification': classifications, 
                'classification_explained': classification_explained
            })
            print(f"============>current_info: {current_info}")
            print(f"============>match_key_res: {match_key_res}")
            match_key = self.parse_match_key_res(match_key_res)
            if match_key is None:
                continue
            match_key = self._post_process_match_key(match_key)
            #如果match_key是'其他'的话，将第一个单元格内容去除，重新匹配
            if match_key is None:
                current_info = row.output_unique_content_str_without_rowtitle()
                if not current_info:
                    continue
                input_data.info = current_info
                match_key_res = match_key_chain.invoke({
                    "current_info": current_info,
                    'classification': classifications, 
                    'classification_explained': classification_explained
                })
                print(f"============>current_info: {current_info}")
                print(f"============>match_key_res: {match_key_res}")
                match_key = self.parse_match_key_res(match_key_res)
                if match_key is None:
                    continue
                match_key = self._post_process_match_key(match_key)
                if match_key is None:
                    continue
            print(f"=======>match key: {match_key}")
            #创建Field类对象存储匹配的因子和相关可选项
            field = Field("row", match_key, row)
            self.field_by_type["row"].append(field)
        
        #by main_title 按mai_title匹配
        for index, label in self.table_structure_by_row.items():
            if label != "main_title":
                continue
            print('&&&&&&&&&&&&&&&&&',index, label)
            row = self.rows.get(index)
            print('rrrrrrrrrrrrrrrrrrrrrrrow',row)
            if row is None:
                continue
            current_info = row.is_all_merged_content
            if current_info is None:
                current_info = row.cell_list[0].value
                if current_info is None:
                    continue
            input_data.info = current_info
            match_key_res = match_key_multi_class_chain.invoke({
                "current_info": current_info,
                'classification': classifications, 
                'classification_explained': classification_explained
            })
            print(f"============>current_info: {current_info}")
            print(f"============>match_key_res: {match_key_res}",type(match_key_res))
            parse_keys = parse_xml_output_without_thinking(match_key_res, ['result'])['result']
            print('~~~~~~~~~~~~~~~~',parse_keys)
            #pdb.set_trace()
            for key in parse_keys:
                if key == '其他':
                    continue
                row.is_pivot = True
                input_data.info = current_info
                #获取key对应的因子可选项内容
                match_key = get_enum_from_maintitle_chain.invoke({
                    'classification':key,
                    'current_info':current_info,
                    'classification_explained': classification_explained
                })
                print('$$$$$$$$$$$$$$$$$$$$$$$$$$$',match_key,'$$$$$$$$$$$$$')
                match_key = parse_xml_output_without_thinking(match_key, ['result'])['result']
                if match_key:
                    match_key = match_key[0]
                    print('mmmmmmmmmmmmmnnnnnnnnnnnnnn',match_key)
                    match_key = self._post_process_match_key(match_key)
                    print('mmmmmmmmmmmmm',match_key)
                    #创建Field类对象存储匹配的因子和相关可选项
                    field = Field("main_title", key, None)
                    field.enum = [match_key]
                    current_info = current_info.replace(match_key, '')
                    self.field_by_type["main_title"].append(field)

        return
    
    #按规定的顺序排列因子
    def sort_factor(self, factor_enums_list):
        sorted_factor_list = []
        for factor in classifications:
            for factor_enum in factor_enums_list:
                if factor == factor_enum['factor']:
                    sorted_factor_list.append({'factor': factor, 'enum': factor_enum['enum']})
                    break
        return sorted_factor_list
    
    #将content的每个单元格对应的费率、因子组合转换为list [因子组合,费率]
    def _traverse_content_table(self):
        contents = []
        for column_index in range(self.content_table_range[-2], self.content_table_range[-1] + 1):
            for row_index in range(self.content_table_range[0], self.content_table_range[1] + 1):
                cell_value = self.columns[str(column_index)].index_2_cell_value.get(str(row_index))
                if cell_value is None:
                    continue
                type_enums_list = []
                main_title_fields = self.field_by_type["main_title"]
                for field in main_title_fields:
                    type_enums_list.append({'factor':field.match_key, 'enum':field.enum[0]})
                
                column_fields = self.field_by_type["column"]
                for field in column_fields:
                    enum = field.index_2_enum.get(str(row_index))
                    if enum is None:
                        continue
                    type_enums_list.append({'factor':field.match_key, 'enum': enum})
                
                row_fields = self.field_by_type["row"]
                for field in row_fields:
                    enum = field.index_2_enum.get(str(column_index))
                    if enum is None:
                        continue
                    type_enums_list.append({'factor':field.match_key, 'enum': enum})
                
                enums = []
                enums_dict_list = self.sort_factor(type_enums_list)
                for enums_dict in enums_dict_list:
                    enums.append(enums_dict['enum'])
                contents.append(["/".join(enums), str(cell_value)])
        return contents
    
    #获取表格全部的factor_enum信息[{'factor':field.match_key, 'enum':concat_enum}]
    def _get_factor_enum_dict(self):
        factor_enum_infos = []
        for field in self.field_by_type["main_title"]:
            concat_enum = field.enum
            factor_enum_infos.append({'factor':field.match_key, 'enum':concat_enum})
        for field in self.field_by_type["column"]:
            concat_enum = field.enum
            factor_enum_infos.append({'factor':field.match_key, 'enum':concat_enum})
        for field in self.field_by_type["row"]:
            concat_enum = field.enum
            factor_enum_infos.append({'factor':field.match_key, 'enum':concat_enum})
        factor_enum_infos = self.sort_factor(factor_enum_infos)
        return factor_enum_infos

    def _flatten(self):
        contents = self._traverse_content_table()
        self.base_table = pd.DataFrame(contents, columns=["因子组合", "费率"])
        self.factor_enum_dict_list = self._get_factor_enum_dict()

    #平铺表格
    def flatten(self):
        #配对因子
        self.match_keys()
        #平铺
        self._flatten()