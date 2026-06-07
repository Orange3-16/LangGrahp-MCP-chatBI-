import asyncio
from build_graph import make_graph

async def test_build_graph():
    """测试build_graph功能"""
    try:
        print("正在创建图...")
        async with make_graph() as graph:
            print("图创建成功！")
            print(f"图类型: {type(graph)}")
            print("测试完成")
    except Exception as e:
        print(f"创建图时出现错误: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_build_graph())
