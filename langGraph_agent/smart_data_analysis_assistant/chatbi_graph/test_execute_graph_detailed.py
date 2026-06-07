import asyncio
import traceback
from build_graph import make_graph
from langchain_core.messages import HumanMessage

async def test_execute_graph():
    """测试execute_graph功能"""
    try:
        print("正在创建图...")
        async with make_graph() as graph:
            print("图创建成功！")
            print(f"图类型: {type(graph)}")
            
            # 测试一个简单的查询
            print("\n测试简单查询...")
            user_input = "查询所有表"
            table_info_message = {
                "role": "user",
                "content": "请先获取数据库中的所有表及其结构信息，然后再回答我的问题：" + user_input
            }
            event_message_list = [table_info_message]
            
            print("发送查询请求...")
            async for event in graph.astream({"messages": event_message_list}, stream_mode="values"):
                print("收到事件:")
                if event["messages"] and event["messages"][-1]:
                    print(f"消息内容: {event['messages'][-1].content}")
                event_message_list.append(event["messages"][-1])
            
            print("测试完成")
    except Exception as e:
        print(f"测试过程中出现错误: {str(e)}")
        traceback.print_exc()

if __name__ == "__main__":
    print("开始测试execute_graph...")
    asyncio.run(test_execute_graph())
