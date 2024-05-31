from dotenv import load_dotenv
load_dotenv()
from src.get_res import get_res

import os

def get_all_file_paths(directory):
    file_paths = []
    for root, _, files in os.walk(directory):
        for file in files:
            file_paths.append(os.path.join(root, file))
    return file_paths



if __name__ == "__main__":
    # file_path = r"/sdata/yaosong/ai-project/insurance_rate/data/single/2.蜗牛如意2号百万医疗保险.xlsx"
    file_path = r"/sdata/zhijiang/ai-project/insurance_rate/data/single/中国人保金医保百万医疗险-费率表.xlsx"
    # 
    # 
    # 
    # 
    # file_path = r"/sdata/yaosong/ai-project/insurance_rate/data/single/test1.xlsx"
    output_dir_path = r"./data/output"

    # origin_url, result_url = get_res(file_path, output_dir_path)
    # print(origin_url)
    # print(result_url)
    # #get_res(file_path, output_dir_path)
    directory = r'/sdata/zhijiang/ai-project/insurance_rate/data/single'
    all_file_paths = get_all_file_paths(directory)
    for path in all_file_paths:
        original_url, result_url = get_res(path, output_dir_path)