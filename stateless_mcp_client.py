# -*- coding: utf-8 -*-
"""交互式地图智能体 - 使用map_search封装的高德MCP工具"""
import asyncio
import os
import json
import re

from agentscope.agent import ReActAgent, UserAgent
from agentscope.formatter import DashScopeChatFormatter
from agentscope.mcp import HttpStatelessClient
from agentscope.model import DashScopeChatModel
from agentscope.tool import Toolkit
from agentscope.message import Msg

# API密钥
GAODE_API_KEY = os.getenv("GAODE_API_KEY", "0bd115daa3976ab7d4b4d1c3bb0036dd")
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "sk-fabdcb62db0e4ab1800efa704bd32314")

async def create_map_search(client):
    """创建map_search函数 - 封装高德MCP调用"""
    
    # 获取高德MCP函数
    maps_geo = await client.get_callable_function("maps_geo")
    maps_text_search = await client.get_callable_function("maps_text_search")
    maps_around_search = await client.get_callable_function("maps_around_search")
    
    async def map_search(query, search_type="auto", location=None, radius=1000):
        """
        封装的高德地图搜索函数
        
        Args:
            query: 搜索关键词或地址
            search_type: 搜索类型，可选值：
                - "auto": 自动判断（默认）
                - "text": 文本搜索（POI搜索）
                - "geo": 地理编码（地址转坐标）
                - "around": 周边搜索
            location: 用于周边搜索的中心位置，格式："经度,纬度" 或 地址字符串
            radius: 周边搜索半径（米），默认1000米
            
        Returns:
            包含搜索结果的结构化字典
        """
        
        # 自动判断搜索类型
        if search_type == "auto":
            if "附近" in query or "周边" in query:
                search_type = "around"
                # 提取中心位置和关键词
                match = re.match(r'(.+?)(?:附近|周边)的?(.+)', query)
                if match:
                    if location is None:
                        location = match.group(1).strip()
                    query = match.group(2).strip()
            elif any(word in query for word in ["省", "市", "区", "路", "街", "号"]):
                search_type = "geo"
            else:
                search_type = "text"
        
        try:
            # 执行搜索
            if search_type == "text":
                result = await maps_text_search(keywords=query)
            elif search_type == "geo":
                result = await maps_geo(address=query)
            elif search_type == "around":
                # 处理位置参数
                if location and not re.match(r'^\s*-?\d+\.?\d*\s*,\s*-?\d+\.?\d*\s*$', location):
                    # 地址转坐标
                    geo_result = await maps_geo(address=location)
                    if geo_result.content:
                        geo_data = json.loads(geo_result.content[0]['text'])
                        location = geo_data['results'][0]['location']
                
                result = await maps_around_search(
                    location=location,
                    keywords=query,
                    radius=radius
                )
            
            # 解析结果
            if result and result.content:
                data = []
                for item in result.content:
                    if isinstance(item, dict) and 'text' in item:
                        try:
                            data.append(json.loads(item['text']))
                        except:
                            data.append(item['text'])
                
                return {
                    "success": True,
                    "type": search_type,
                    "query": query,
                    "data": data
                }
            
        except Exception as e:
            return {
                "success": False,
                "type": search_type,
                "query": query,
                "error": str(e)
            }
        
        return {"success": False, "type": search_type, "query": query}
    
    return map_search

async def create_map_agent():
    """创建使用map_search的地图智能体"""
    
    # 创建高德MCP客户端
    client = HttpStatelessClient(
        name="amap",
        transport="streamable_http",
        url=f"https://mcp.amap.com/mcp?key={GAODE_API_KEY}",
    )
    
    # 创建map_search函数
    map_search_func = await create_map_search(client)
    
    # 创建工具包并注册MCP客户端
    toolkit = Toolkit()
    await toolkit.register_mcp_client(client)
    
    # 创建智能体
    agent = ReActAgent(
        name="地图助手",
        sys_prompt="""你是一个专业的地图服务助手，专门帮助用户解决地图相关的问题。

## 你的能力
1. 地点搜索：搜索特定地点、POI（兴趣点）
2. 地理编码：将地址转换为经纬度坐标
3. 周边搜索：查找某个地点周边的设施（餐厅、酒店、银行等）
4. 路线规划：提供出行路线建议

## 工具使用指南
你可以使用以下高德地图工具：
- maps_text_search: 文本搜索，用于搜索地点、POI
- maps_geo: 地理编码，将地址转换为坐标
- maps_around_search: 周边搜索，查找某个位置周边的设施
- maps_direction_*: 路线规划工具

## 响应要求
1. 提供清晰、有用的信息
2. 如果搜索结果包含多个选项，列出最重要的几个
3. 提供地址、坐标等关键信息
4. 如果搜索失败，友好地提示用户并提供替代方案
5.The input locations maybe not specific，So you MUST ftrst
use the 'maps_text_search'function to get the complete and
accurate address.After that，you can use the 'maps_geo'
function to get the latitude and longitude of the location
2． DON'T make any assumptions!All the locations (include
latitude and longitude)you use should be obtained from the
tools
3． Sometimes，there maybe multiple locations for the same name，
once you feel the search result is not accurate，you should
research with different keywords or use generate_response
function tO ask for more information
4． You can use Gaode API tools to obtain POI related
pictures

## 特别注意
当用户询问"XX附近的YY"时，使用maps_around_search工具
当用户询问具体地址的坐标时，使用maps_geo工具
对于一般的地点查询，使用maps_text_search工具""",
        model=DashScopeChatModel(
            model_name="qwen-max",
            api_key=DASHSCOPE_API_KEY,
        ),
        formatter=DashScopeChatFormatter(),
        toolkit=toolkit,
    )
    
    return agent, map_search_func

async def interactive_chat():
    """交互式对话主函数"""
    
    print("=" * 60)
    print("地图智能体 - 交互式对话系统")
    print("=" * 60)
    print("说明：")
    print("1. 输入 '退出' 或 'exit' 结束对话")
    print("2. 输入 '帮助' 或 'help' 查看使用说明")
    print("3. 支持中文自然语言查询")
    print("=" * 60)
    
    # 创建智能体和map_search函数
    print("\n正在初始化地图智能体...")
    agent, map_search_func = await create_map_agent()
    user = UserAgent(name="用户")
    
    print("智能体已就绪！开始对话吧！\n")
    
    # 初始消息
    msg = Msg(
        name="系统",
        content="你好！我是地图助手，可以帮你搜索地点、查找周边设施、获取坐标等。有什么可以帮你的吗？",
        role="assistant"
    )
    
    print(f"地图助手: {msg.content}")
    
    # 交互循环
    while True:
        try:
            # 获取用户输入
            user_input = input("\n你: ").strip()
            
            if not user_input:
                continue
                
            # 检查退出命令
            if user_input.lower() in ["退出", "exit", "quit", "q"]:
                print("\n地图助手: 感谢使用，再见！")
                break
                
            # 检查帮助命令
            if user_input.lower() in ["帮助", "help", "?"]:
                print("\n地图助手: 我可以帮你：")
                print("1. 搜索地点：'搜索阿里云谷园区'")
                print("2. 获取坐标：'上海市人民广场的坐标是多少'")
                print("3. 查找周边：'阿里云谷园区附近有什么咖啡厅'")
                print("4. 路线查询：'从北京到上海怎么走'")
                print("5. 距离测量：'北京到上海有多远'")
                continue
            
            # 处理用户输入
            msg = Msg(name="用户", content=user_input, role="user")
            
            # 获取智能体响应
            print("\n地图助手: 思考中...")
            response = await agent(msg)
            
            # 显示响应
            if hasattr(response, 'content'):
                content = response.content
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and 'text' in item:
                            print(f"地图助手: {item['text']}")
                        elif isinstance(item, str):
                            print(f"地图助手: {item}")
                elif isinstance(content, str):
                    print(f"地图助手: {content}")
                else:
                    print(f"地图助手: {str(content)[:500]}...")
            else:
                print(f"地图助手: {str(response)[:500]}...")
                
        except KeyboardInterrupt:
            print("\n\n地图助手: 对话已中断，再见！")
            break
        except Exception as e:
            print(f"\n地图助手: 抱歉，出错了: {str(e)}")
            print("请重新输入你的问题。")

async def main():
    """主函数"""
    await interactive_chat()

if __name__ == "__main__":
    asyncio.run(main())
