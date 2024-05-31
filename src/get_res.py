import openpyxl
from src.table import Table
from src.merge_table import merge_base_table_dict, merge_table_n_write
from src.upload_data import upload_origin_file, upload_result_file
import os
import pandas as pd
import pdb
import time
import requests
def get_res(file_path, output_dir_path):
    #获取原始excel文件url
    origin_url = upload_origin_file(file_path)
    #创建输出文件路径（加时间戳）
    workbook = openpyxl.load_workbook(file_path)
    timestamp = int(time.time())
    filename = os.path.basename(file_path).replace('.xlsx',f'_flatten_{timestamp}.xlsx').replace('.csv',f'_flatten_{timestamp}.xlsx')
    output_path = os.path.join(output_dir_path, filename)
    if not os.path.exists(output_path):
        # 创建输出文件路径的目录
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
    writer = pd.ExcelWriter(output_path)

    #按sheet处理表格，中间结果保存到base_table_dict
    base_table_dict = {}
    for sheet_name in workbook.sheetnames:
        #获取base_name，同一个责任需要合并表格，例如：基本责任_1，基本责任_2
        if '_' in sheet_name:
            base_name = sheet_name.replace(sheet_name.split('_')[-1],'').replace('_','')
        else:
            base_name = sheet_name
        print(base_name)
        print(sheet_name)
        #pdb.set_trace()

        #创建Table类对象
        table = Table(sheet_name)

        #读取sheet内容
        table.load_table(workbook[sheet_name])
        #pdb.set_trace()

        #识别表格结构
        table.recognize_table_structure()
        #pdb.set_trace()

        #平铺表格
        table.flatten()

        #合并base_table
        base_table_dict = merge_base_table_dict(base_table_dict, base_name, table)
    
    #合并所有表格并write文件
    writer = merge_table_n_write(base_table_dict, writer)
    writer._save()
    writer.close()
    result_url = upload_result_file(output_path)
    return origin_url, result_url