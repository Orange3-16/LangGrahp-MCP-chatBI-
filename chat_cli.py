"""
命令行聊天工具
直接输入聊天内容，获得聊天助手的回复
"""
import requests
import json


def main():
    print("ChatBI 数据分析智能助手")
    print("输入 'exit' 退出聊天")
    print("=" * 50)

    # 初始化聊天历史
    history = []

    while True:
        # 获取用户输入
        user_input = input("你: ")

        # 检查是否退出
        if user_input.lower() == 'exit':
            print("再见！")
            break

        # 构建请求数据
        data = {
            "user_id": "cli_user",
            "message": user_input,
            "history": history
        }

        try:
            # 发送请求
            response = requests.post(
                "http://localhost:9008/chatbi_service",
                json=data,
                headers={"Content-Type": "application/json"}
            )

            # 解析响应
            if response.status_code == 200:
                result = response.json()
                assistant_reply = result.get("message", "抱歉，我无法理解你的问题。")
                print(f"助手: {assistant_reply}")

                # 更新聊天历史
                history.append({"role": "user", "content": user_input})
                history.append({"role": "assistant", "content": assistant_reply})
            else:
                print(f"错误: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"连接错误: {str(e)}")
            print("请确保主应用服务正在运行 (python simple_api.py)")


if __name__ == "__main__":
    main()