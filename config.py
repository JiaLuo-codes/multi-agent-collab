"""配置"""
import os
from dotenv import load_dotenv
load_dotenv()

DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY")
MODEL_NAME = "qwen-plus"
TEMPERATURE = 0.7
