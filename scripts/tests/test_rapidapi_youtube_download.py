import http.client
import json
import urllib.request
from urllib.parse import urlencode


# 建议把 key 放到环境变量里，这里为了测试直接写死
RAPIDAPI_KEY = "8d120f3cf8msh03e3f63d9190a01p1102bejsn723218ffa275"
RAPIDAPI_HOST = "yt-api.p.rapidapi.com"


def get_video_info(video_id: str, cgeo: str = "DE") -> dict:
    """调用 RapidAPI 获取视频信息和下载地址"""
    conn = http.client.HTTPSConnection(RAPIDAPI_HOST)

    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": RAPIDAPI_HOST,
    }

    path = f"/dl?{urlencode({'id': video_id, 'cgeo': cgeo})}"

    print(f"[INFO] 请求: https://{RAPIDAPI_HOST}{path}")
    conn.request("GET", path, headers=headers)

    res = conn.getresponse()
    body = res.read()
    conn.close()

    print(f"[INFO] HTTP 状态码: {res.status}")
    if res.status != 200:
        raise RuntimeError(f"API 请求失败，status={res.status}, body={body[:500]!r}")

    data = json.loads(body.decode("utf-8"))
    return data


def pick_download_url(info: dict) -> str:
    """
    从返回结果里挑一个 mp4 下载地址（优先 720p/360p 的整合流）
    """
    formats = info.get("formats", []) or []

    # 1) 尝试优先 itag=22 (720p mp4)
    for f in formats:
        if f.get("itag") == 22:
            return f["url"]

    # 2) 再尝试 itag=18 (360p mp4)
    for f in formats:
        if f.get("itag") == 18:
            return f["url"]

    # 3) 再退而求其次：第一个 mimeType 里含 "video/mp4" 的
    for f in formats:
        if "mimeType" in f and "video/mp4" in f["mimeType"]:
            return f["url"]

    raise RuntimeError("没有找到合适的 mp4 下载地址")


def download_file(url: str, output_path: str):
    """通过返回的直链把文件下载到本地"""
    print(f"[INFO] 开始下载: {url[:120]}...")
    print(f"[INFO] 保存到: {output_path}")

    # 简单起见用 urlretrieve（小脚本够用）
    urllib.request.urlretrieve(url, output_path)

    print("[INFO] 下载完成")


def main():
    # 这里用你示例里的视频 ID
    video_id = "ZkDLSxKz0Wc"

    # 1. 调用 RapidAPI，拿到 JSON
    info = get_video_info(video_id)

    print("[INFO] API 返回 status:", info.get("status"))
    print("[INFO] 标题:", info.get("title"))
    print("[INFO] 时长(秒):", info.get("lengthSeconds"))

    # 2. 选择一个下载地址
    download_url = pick_download_url(info)

    # 3. 下载到当前目录，文件名简单用 <id>.mp4
    output_path = f"{video_id}.mp4"
    download_file(download_url, output_path)


if __name__ == "__main__":
    main()