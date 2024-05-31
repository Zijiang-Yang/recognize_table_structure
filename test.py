# <Table>
#     <Row>
#         <Cell><Data ss:Type="String">Header1</Data></Cell>
#         <Cell><Data ss:Type="String">Header2</Data></Cell>
#     </Row>
#     <Row>
#         <Cell><Data ss:Type="String">Data1</Data></Cell>
#         <Cell><Data ss:Type="String">Data2</Data></Cell>
#     </Row>
# </Table>
from src.make_dataset import get_split_dict, get_select_rows
from dotenv import load_dotenv
load_dotenv()

if __name__ == "__main__":
    command = "SELECT DISTINCT info, model_output FROM flatten_table_all_model_prompt WHERE custom_model_name = 'TABLE_STRUCTURE_RECOGNIZE' LIMIT 10"
    rows = get_select_rows(command)
    for index, row in iter(rows):
        text = row[0]
        label = row[1]
        result_dict = get_split_dict(text, label)
        print(result_dict)

