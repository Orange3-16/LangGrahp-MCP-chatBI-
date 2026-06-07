from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

class UserInput(BaseModel):
    user_id: str
    message: str
    history: list[dict]

@app.post("/chatbi_service")
async def chatbi_server(user_input: UserInput):
    print("user_input:", user_input)
    user_id = user_input.user_id
    user_message = user_input.message
    history = user_input.history
    history.append({"role": "user", "content": user_message})
    print(f"用户Id:{user_id},本轮输入:{user_message},历史记录:{history}")
    
    # 简单的响应
    result = f"你好，{user_id}！你说：{user_message}"
    print("本轮回复:", result)
    return {"message": result}

@app.get("/")
async def root():
    return {"message": "ChatBI 数据分析智能助手服务已启动"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9008)