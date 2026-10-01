#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scraper.py —— 公考职位表抓取 / 清洗 / 生成 data.json
================================================================================
用途
    从「国家公务员局国考专题网站」「江苏先锋网」「江苏省人力资源和社会保障厅」
    及江苏各设区市组织部/人社局等**官方渠道**，自动发现在线发布的职位表
    附件（.xlsx / .xls / .zip），下载并用 pandas 解析、清洗，最终生成
    前端 index.html 直接可用的 data.json。

设计原则（务必遵守）
    1. 只抓官方发布的数据，**绝不编造、不推断任何职位信息**；
    2. 遵守 robots.txt，请求间隔默认 3 秒（如对方声明 Crawl-delay 则取更大值），
       失败重试采用指数退避，避免对官网造成压力；
    3. 找不到/抓不到数据时，**保留上一次的 data.json 不变**，只在 meta.warnings
       中写明原因并以非零退出码提示，绝不写入伪造数据。

常用命令
    # 1) 联网自动抓取（GitHub Actions 每天运行的就是这一条）
    python scraper.py

    # 2) 用本地已下载的官方职位表生成 data.json（推荐本地使用，最稳）
    python scraper.py --local 职位表.xlsx --exam-type 江苏省考 --year 2026 \
        --source-url https://www.jszzb.gov.cn/xxx.html

    # 3) 只检查官网有没有新附件，不下载
    python scraper.py --check-only

    # 4) 输出调试信息
    python scraper.py --verbose

    # 5) 自检（不联网、不写文件，仅验证解析逻辑）
    python scraper.py --selftest
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import logging
import os
import re
import sys
import time
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import unquote, urljoin, urlparse
from urllib.robotparser import RobotFileParser

# --------------------------------------------------------------------------- #
# 可选依赖：requests 缺失时自动退回标准库 urllib，保证脚本在最小环境下也能跑
# --------------------------------------------------------------------------- #
try:
    import requests  # type: ignore
    HAS_REQUESTS = True
except Exception:  # pragma: no cover
    import urllib.error
    import urllib.request
    HAS_REQUESTS = False

# 在证书链异常的政府站点上我们会主动放宽 TLS 校验（并自行记录日志），
# 这里关掉 urllib3 的重复告警，避免刷屏。
if HAS_REQUESTS:  # pragma: no cover
    try:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    except Exception:
        pass

try:
    import pandas as pd
except Exception:  # pragma: no cover
    print("[FATAL] 缺少 pandas，请先执行：pip install -r requirements.txt", file=sys.stderr)
    raise

# =========================================================================== #
#                                  配  置
# =========================================================================== #

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_JSON = os.path.join(BASE_DIR, "data.json")           # 输出文件
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")           # 附件下载目录
CACHE_DIR = os.path.join(BASE_DIR, "downloads", ".cache")    # 页面 HTML 缓存

# HTTP 头只能用 latin-1 编码，因此 User-Agent 必须是纯 ASCII！
# （踩过的坑：UA 里写了中文，导致 requests 在发送请求头时抛
#   'latin-1' codec can't encode characters —— 所有能连通的站点全部失败）
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0 Safari/537.36 "
    "GongkaoJobQueryBot/1.0 (+https://github.com/; respects robots.txt)"
)

# 同一域名两次请求之间的最小间隔（秒）——避免给官网造成压力
DEFAULT_DELAY = 3.0
DEFAULT_TIMEOUT = 30
MAX_RETRY = 3

# local timezone（GitHub Actions 跑在 UTC，这里统一转成北京时间展示）
CST = timezone(timedelta(hours=8))

# 江苏 13 个设区市 + 常用别名，用于判定"工作地点是否在江苏"
JIANGSU_KEYWORDS = [
    "江苏", "南京", "无锡", "徐州", "常州", "苏州", "南通", "连云港",
    "淮安", "盐城", "扬州", "镇江", "泰州", "宿迁",
]

# 需要重点关注的岗位类别：生物科学（师范）可能匹配的专业目录
MAJOR_TAGS = ["生物科学", "生物科学类", "基础理学类", "教育类", "不限专业", "相近专业"]

# --------------------------------------------------------------------------- #
# 数据源配置：只允许这些**官方**域名被访问（白名单，防止误抓第三方培训网站）
# --------------------------------------------------------------------------- #
@dataclass
class Source:
    name: str                                  # 数据源名称（写入 meta）
    exam_type: str                             # 考试类型：国考 / 江苏省考 / 江苏省考(市级)
    year: Optional[int]                        # 默认年度（可从网页标题中自动纠正）
    entry_pages: List[str]                     # 入口页面（公告列表页 / 专题页）
    link_keywords: List[str]                   # 入口页里哪些链接值得跟进
    allowed_hosts: List[str]                   # 允许访问的域名（白名单）
    depth: int = 2                             # 跟进层级：2 = 列表页 -> 公告页 -> 附件


SOURCES: List[Source] = [
    # ---------------- 国家公务员考试 ----------------
    Source(
        name="国家公务员局·中央机关及其直属机构考试录用公务员专题（相关下载）",
        exam_type="国考",
        year=None,                             # 从页面标题/附件名中自动识别年度
        entry_pages=[
            # 实测：bm.scs.gov.cn 的 443 端口拒绝连接，80 端口可用；kl2025/kl2024 已下线(404)
            # ⚠ 国考专题站目前是纯 JS 应用（页面 2~4KB、0 个链接），静态爬虫拿不到数据；往年它是静态页。
            #   tools/probe_new_cycle.py 会在发布当天自动判定它属于哪类，据此决定是否需要浏览器渲染。
            "http://bm.scs.gov.cn/kl2026/",
            "http://bm.scs.gov.cn/kl2027/",
            "http://bm.scs.gov.cn/pp/gkweb/core/web/ui/business/download/gkdownloads.html",
            "https://www.scs.gov.cn/",
        ],
        link_keywords=["相关下载", "职位表", "招考简章", "考试录用", "公告", "下载"],
        allowed_hosts=["bm.scs.gov.cn", "www.scs.gov.cn", "scs.gov.cn", "dl.scs.gov.cn"],
        depth=2,
    ),
    # ---------------- 江苏省公务员考试 ----------------
    Source(
        name="江苏先锋网·江苏省考试录用公务员专题",
        exam_type="江苏省考",
        year=None,
        entry_pages=[
            "https://www.jszzb.gov.cn/",
            "https://www.jszzb.gov.cn/col/col1001/index.html",  # 通知公告
            "http://www.jszzb.gov.cn/",
        ],
        link_keywords=["公务员", "考试录用", "公告", "职位表", "简章", "下载"],
        allowed_hosts=["www.jszzb.gov.cn", "jszzb.gov.cn"],
        depth=2,
    ),
    Source(
        name="江苏省人力资源和社会保障厅·公务员招录（岗位信息/省考专题）",
        exam_type="江苏省考",
        year=None,
        # 实测（2026-10）：江苏省考职位表在「岗位信息」栏目 col92919 的 3 篇文章页里
        #   · 省级机关职位表.xls      · 各地职位表.zip（13 市）      · 垂管单位职位表（统计/监狱戒毒）
        # 专题栏目 id 每轮会变，所以同时把"更多专题"列表页作为入口，靠关键词跟到新专题
        entry_pages=[
            "http://jshrss.jiangsu.gov.cn/col/col92919/index.html",   # 岗位信息（职位表所在栏目）
            "http://jshrss.jiangsu.gov.cn/col/col92911/index.html",   # 本轮省考专题
            "http://jshrss.jiangsu.gov.cn/col/col79436/index.html",   # 专题专栏列表（找下一轮专题）
            "http://jshrss.jiangsu.gov.cn/col/col57253/index.html",   # 江苏人事考试网
            "https://jshrss.jiangsu.gov.cn/",
        ],
        link_keywords=["公务员", "考试录用", "公告", "职位表", "招录", "岗位信息", "专题"],
        allowed_hosts=["jshrss.jiangsu.gov.cn"],
        depth=3,
    ),
    # ---------------- 各设区市（市级岗位发布渠道） ----------------
    Source(
        name="南京市人力资源和社会保障局",
        exam_type="江苏省考(南京市)",
        year=None,
        entry_pages=["https://rsj.nanjing.gov.cn/"],
        link_keywords=["公务员", "考试录用", "职位表", "公告"],
        allowed_hosts=["rsj.nanjing.gov.cn", "www.nanjing.gov.cn"],
        depth=2,
    ),
    Source(
        name="苏州市人力资源和社会保障局",
        exam_type="江苏省考(苏州市)",
        year=None,
        # 实测：rlsbj.suzhou.gov.cn 不存在；hrss.suzhou.gov.cn 存在但有重定向环，用 http 入口
        entry_pages=["http://hrss.suzhou.gov.cn/"],
        link_keywords=["公务员", "考试录用", "职位表", "公告"],
        allowed_hosts=["hrss.suzhou.gov.cn", "www.suzhou.gov.cn"],
        depth=2,
    ),
    Source(
        name="无锡市人力资源和社会保障局",
        exam_type="江苏省考(无锡市)",
        year=None,
        entry_pages=["https://hrss.wuxi.gov.cn/"],
        link_keywords=["公务员", "考试录用", "职位表", "公告"],
        allowed_hosts=["hrss.wuxi.gov.cn", "www.wuxi.gov.cn"],
        depth=2,
    ),
    Source(
        name="常州市人力资源和社会保障局",
        exam_type="江苏省考(常州市)",
        year=None,
        entry_pages=["https://rsj.changzhou.gov.cn/"],
        link_keywords=["公务员", "考试录用", "职位表", "公告"],
        allowed_hosts=["rsj.changzhou.gov.cn", "www.changzhou.gov.cn"],
        depth=2,
    ),
    Source(
        name="南通市人力资源和社会保障局",
        exam_type="江苏省考(南通市)",
        year=None,
        entry_pages=["https://rsj.nantong.gov.cn/"],
        link_keywords=["公务员", "考试录用", "职位表", "公告"],
        allowed_hosts=["rsj.nantong.gov.cn", "www.nantong.gov.cn"],
        depth=2,
    ),
    Source(
        name="扬州市人力资源和社会保障局",
        exam_type="江苏省考(扬州市)",
        year=None,
        # 实测：rsj.yangzhou.gov.cn 不存在，正确域名是 hrss.yangzhou.gov.cn（2026-10 实测 200）
        entry_pages=["https://hrss.yangzhou.gov.cn/"],
        link_keywords=["公务员", "考试录用", "职位表", "公告"],
        allowed_hosts=["hrss.yangzhou.gov.cn", "www.yangzhou.gov.cn"],
        depth=2,
    ),
    Source(
        name="泰州市人力资源和社会保障局",
        exam_type="江苏省考(泰州市)",
        year=None,
        entry_pages=["https://rsj.taizhou.gov.cn/"],
        link_keywords=["公务员", "考试录用", "职位表", "公告"],
        allowed_hosts=["rsj.taizhou.gov.cn", "www.taizhou.gov.cn"],
        depth=2,
    ),
    Source(
        name="盐城市人力资源和社会保障局",
        exam_type="江苏省考(盐城市)",
        year=None,
        entry_pages=["https://jsychrss.yancheng.gov.cn/"],
        link_keywords=["公务员", "考试录用", "职位表", "公告"],
        allowed_hosts=["jsychrss.yancheng.gov.cn", "www.yancheng.gov.cn"],
        depth=2,
    ),
    Source(
        name="镇江市人力资源和社会保障局",
        exam_type="江苏省考(镇江市)",
        year=None,
        entry_pages=["https://hrss.zhenjiang.gov.cn/"],
        link_keywords=["公务员", "考试录用", "职位表", "公告"],
        allowed_hosts=["hrss.zhenjiang.gov.cn", "www.zhenjiang.gov.cn"],
        depth=2,
    ),
    Source(
        name="淮安市人力资源和社会保障局",
        exam_type="江苏省考(淮安市)",
        year=None,
        entry_pages=["https://rsj.huaian.gov.cn/"],
        link_keywords=["公务员", "考试录用", "职位表", "公告"],
        allowed_hosts=["rsj.huaian.gov.cn", "www.huaian.gov.cn"],
        depth=2,
    ),
    Source(
        name="宿迁市人力资源和社会保障局",
        exam_type="江苏省考(宿迁市)",
        year=None,
        entry_pages=["https://sqhrss.suqian.gov.cn/"],
        link_keywords=["公务员", "考试录用", "职位表", "公告"],
        allowed_hosts=["sqhrss.suqian.gov.cn", "www.suqian.gov.cn"],
        depth=2,
    ),
    Source(
        name="徐州市人力资源和社会保障局",
        exam_type="江苏省考(徐州市)",
        year=None,
        entry_pages=["https://hrss.xz.gov.cn/"],
        link_keywords=["公务员", "考试录用", "职位表", "公告"],
        allowed_hosts=["hrss.xz.gov.cn", "www.xz.gov.cn"],
        depth=2,
    ),
    Source(
        name="连云港市人力资源和社会保障局",
        exam_type="江苏省考(连云港市)",
        year=None,
        entry_pages=["https://rsj.lyg.gov.cn/"],
        link_keywords=["公务员", "考试录用", "职位表", "公告"],
        allowed_hosts=["rsj.lyg.gov.cn", "www.lyg.gov.cn"],
        depth=2,
    ),
]

# --------------------------------------------------------------------------- #
# 官方职位表表头 -> 本工具标准字段 的别名映射
# 说明：国考、江苏省考、各市职位表的表头每年都略有差异，这里做归一化。
# --------------------------------------------------------------------------- #
COLUMN_ALIASES: Dict[str, List[str]] = {
    "职位代码":       ["职位代码", "职位编码", "岗位代码", "职位序号", "招考职位代码", "代码"],
    "招录机关":       ["招录机关", "部门名称", "招录单位", "招聘单位", "单位名称", "主管部门", "机关名称"],
    "用人司局/单位":  ["用人司局", "用人单位", "内设机构", "招考单位", "处室", "科室", "部门"],
    "职位名称":       ["招考职位", "职位名称", "岗位名称", "招聘岗位", "招考岗位", "职位"],
    "招录人数":       ["招考人数", "招录人数", "计划录用人数", "招聘人数", "计划数", "人数"],
    # 注意顺序：江苏省考表里同时有「地区代码」和「地区名称」，必须让"地区名称"先命中，
    # 否则工作地点会变成 6 位数字的地区代码（已踩过）
    "工作地点":       ["工作地点", "工作地", "工作所在地", "职位分布", "地区名称", "所属地区", "地区", "单位地址"],
    "学历要求":       ["学历要求", "学历", "学历条件"],
    "学位要求":       ["学位要求", "学位"],
    "专业要求原文":   ["专业", "专业要求", "所学专业", "专业条件", "专业类别"],
    "政治面貌":       ["政治面貌", "政治条件"],
    "基层工作最低年限": ["基层工作最低年限", "基层工作经历", "基层年限", "工作经历", "是否要求基层工作经历"],
    "身份要求":       ["身份要求", "招考对象", "报考身份", "考生身份", "面向对象", "招聘对象"],
    "户籍/生源要求":  ["户籍要求", "户籍", "生源", "户籍或生源地", "生源地要求"],
    "其他条件":       ["其他条件", "其他", "其它", "其它条件", "其他要求", "报考条件"],
    "考试类别":       ["考试类别", "考试科目", "职位类别", "试卷类别", "专业考试科目"],
    "面试比例":       ["面试人员比例", "面试比例", "面试人选比例", "开考比例"],
    "备注":           ["备注", "其他说明"],
    "职位简介":       ["职位简介", "职位描述", "岗位简介", "说明"],
    "咨询电话":       ["咨询电话1", "咨询电话", "联系电话", "电话", "咨询电话2"],
    "落户地点":       ["落户地点", "落户"],
    "机构性质":       ["机构性质", "单位性质", "机构层级"],
    "服务基层项目工作经历": ["服务基层项目工作经历", "服务基层项目", "基层项目"],
}

# 前端展示 / CSV 导出的字段顺序
OUTPUT_FIELDS = [
    "考试类型", "年度", "职位代码", "招录机关", "用人司局/单位", "职位名称", "招录人数",
    "工作地点", "学历要求", "学位要求", "专业要求原文", "专业目录归属", "政治面貌",
    "基层工作最低年限", "身份要求", "户籍/生源要求", "其他条件", "考试类别", "面试比例",
    "备注", "咨询电话", "来源链接", "匹配结论", "匹配说明", "需电话咨询",
]

log = logging.getLogger("scraper")


def init_console() -> None:
    """
    让脚本在 Windows（默认 GBK 控制台）下也不会因为中文/特殊字符抛
    UnicodeEncodeError：
      * 控制台本身能表示中文（GBK/UTF-8）时，保持原编码，仅把不可编码字符替换为 '?'；
      * 控制台是 ascii 等无法表示中文的编码时，强制切换为 UTF-8。
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            enc = (getattr(stream, "encoding", "") or "").lower()
            if enc in ("", "ascii", "ansi_x3.4-1968", "us-ascii"):
                stream.reconfigure(encoding="utf-8", errors="replace")
            else:
                stream.reconfigure(errors="replace")
        except Exception:
            pass


init_console()


# =========================================================================== #
#                          一、HTTP 访问层（礼貌抓取）
# =========================================================================== #

class PoliteSession:
    """
    礼貌的 HTTP 会话：
      * 同一域名请求间隔 >= max(DEFAULT_DELAY, robots 声明的 Crawl-delay)
      * 遵守 robots.txt（Disallow 的路径直接跳过）
      * 3 次重试 + 指数退避
      * 只允许访问白名单域名
    """

    def __init__(self, delay: float = DEFAULT_DELAY, timeout: int = DEFAULT_TIMEOUT,
                 allowed_hosts: Optional[Iterable[str]] = None):
        self.delay = delay
        self.timeout = timeout
        self.allowed_hosts = set(allowed_hosts or [])
        self.strict_tls = False                        # 默认：证书链异常时对该域名降级重试
        self.insecure_hosts: set = set()               # 已降级的域名（只读公开页面，不发送凭据）
        self._last_request: Dict[str, float] = {}      # host -> 上次请求时间
        self._robots: Dict[str, Optional[RobotFileParser]] = {}
        self._crawl_delay: Dict[str, float] = {}
        self.skipped: List[str] = []                   # 被 robots.txt 拒绝的 URL
        if HAS_REQUESTS:
            self.session = requests.Session()
            self.session.max_redirects = 6             # 政府站偶有重定向环，尽早失败而不是死等
            self.session.headers.update({
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9",
            })
        else:
            self.session = None

    # ---------------- 基础：节流 + 重试 ---------------- #
    def _throttle(self, host: str) -> None:
        wait = max(self.delay, self._crawl_delay.get(host, 0.0))
        last = self._last_request.get(host)
        if last is not None:
            gap = time.time() - last
            if gap < wait:
                time.sleep(round(wait - gap, 2))
        self._last_request[host] = time.time()

    def _raw_get(self, url: str, retry_4xx: bool = True) -> Tuple[Optional[bytes], Optional[str]]:
        """
        返回 (内容字节, content-type)；失败返回 (None, None)。

        特例：不少政府站点的证书链有问题（自签名中间证书、证书主机名不匹配），
        但页面本身是公开信息。这里在**证书校验失败**时对该域名降级重试一次
        （仅 GET 公开页面，不发送任何凭据），并在日志中明确记录。
        如需强制严格校验，用 --strict-tls。
        """
        host = urlparse(url).netloc
        attempt = 0
        while attempt < MAX_RETRY:
            attempt += 1
            try:
                if HAS_REQUESTS:
                    r = self.session.get(url, timeout=self.timeout, allow_redirects=True,
                                         verify=(host not in self.insecure_hosts))
                    if not retry_4xx and r.status_code in (404, 410):
                        return None, None          # robots.txt 不存在是常态，不值得重试 3 次
                    if r.status_code >= 400:
                        raise RuntimeError("HTTP %s" % r.status_code)
                    return r.content, r.headers.get("Content-Type", "")
                else:  # pragma: no cover - 仅在无 requests 环境走这里
                    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
                    with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                        return resp.read(), resp.headers.get("Content-Type", "")
            except Exception as exc:
                msg = str(exc)
                # 证书问题 -> 降级一次（不消耗重试次数）
                if (not self.strict_tls and host not in self.insecure_hosts
                        and "CERTIFICATE_VERIFY_FAILED" in msg):
                    self.insecure_hosts.add(host)
                    log.warning("  %s 证书校验失败，本次运行对该域名放宽 TLS 校验"
                                "（只读取公开页面，不发送任何凭据）", host)
                    attempt -= 1
                    continue
                if attempt >= MAX_RETRY:
                    log.warning("  请求失败（已重试 %d 次）：%s -> %s", MAX_RETRY, url, exc)
                    return None, None
                backoff = 2 ** attempt
                log.info("  请求异常(%s)，%d 秒后重试：%s", exc, backoff, url)
                time.sleep(backoff)
        return None, None

    # ---------------- robots.txt ---------------- #
    def robots_allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        host = parsed.netloc
        if host not in self._robots:
            robots_url = "%s://%s/robots.txt" % (parsed.scheme, host)
            rp: Optional[RobotFileParser] = None
            content, _ = self._raw_get(robots_url, retry_4xx=False)
            if content:
                try:
                    rp = RobotFileParser()
                    rp.parse(content.decode("utf-8", errors="ignore").splitlines())
                    cd = rp.crawl_delay(USER_AGENT) or rp.crawl_delay("*")
                    if cd:
                        self._crawl_delay[host] = float(cd)
                        log.info("  robots.txt 声明 Crawl-delay=%s 秒（%s）", cd, host)
                except Exception as exc:
                    log.info("  robots.txt 解析失败（%s），按允许处理", exc)
                    rp = None
            else:
                log.info("  未取到 robots.txt（%s），按允许处理", host)
            self._robots[host] = rp

        rp = self._robots[host]
        if rp is None:
            return True
        ok = rp.can_fetch(USER_AGENT, url) or rp.can_fetch("*", url)
        if not ok:
            log.warning("  [robots] robots.txt 禁止抓取，已跳过：%s", url)
            self.skipped.append(url)
        return ok

    # ---------------- 对外：取文本 / 取二进制 ---------------- #
    def get_text(self, url: str, check_robots: bool = True) -> Optional[str]:
        host = urlparse(url).netloc
        if self.allowed_hosts and host not in self.allowed_hosts:
            log.info("  跳过非白名单域名：%s", url)
            return None
        if check_robots and not self.robots_allowed(url):
            return None
        self._throttle(host)
        log.info("  GET %s", url)
        content, ctype = self._raw_get(url)
        if content is None:
            return None
        # 自动识别编码：优先页面声明的 charset，其次 utf-8，最后 gb18030（政府网站常见）
        text = None
        head = content[:4096].decode("ascii", errors="ignore").lower()
        m = re.search(r'charset=["\']?([\w-]+)', head)
        encodings = [m.group(1)] if m else []
        encodings += ["utf-8", "gb18030"]
        for enc in encodings:
            try:
                text = content.decode(enc)
                break
            except Exception:
                continue
        return text

    def get_bytes(self, url: str) -> Optional[bytes]:
        host = urlparse(url).netloc
        if self.allowed_hosts and host not in self.allowed_hosts:
            log.info("  跳过非白名单域名：%s", url)
            return None
        if not self.robots_allowed(url):
            return None
        self._throttle(host)
        log.info("  DOWNLOAD %s", url)
        content, _ = self._raw_get(url)
        return content


# =========================================================================== #
#                        二、发现附件（职位表 Excel）
# =========================================================================== #

EXCEL_EXT = (".xlsx", ".xls", ".xlsm")
ARCHIVE_EXT = (".zip", ".rar", ".7z")
ATTACH_KEYWORDS = ["职位表", "职位简介", "招考简章", "招录职位", "岗位表", "职位信息表", "职位一览表"]
# 只抓"公务员"相关：附件标题或所在页面标题必须命中其中之一
ATTACH_REQUIRE = ["公务员", "考试录用"]
# 明显不是职位表的附件，避免误下载
# （实测教训：不排除"事业单位"就会把市属事业单位招聘岗位表当成公务员职位表抓进来）
ATTACH_BLOCKLIST = ["专业目录", "考试大纲", "报名登记表", "报名推荐表", "准考证", "体检", "承诺书", "答题卡",
                    "事业单位", "编外", "劳务派遣", "公益性岗位", "辅警", "社区工作者", "专职网格员",
                    "聘用制", "政府购买服务", "国有企业", "校园招聘", "实习"]


@dataclass
class Attachment:
    url: str
    title: str
    page_url: str          # 发现该附件的页面（作为"来源链接"）
    source_name: str
    exam_type: str
    year: Optional[int]
    kind: str = "jobs"     # jobs=职位表 | phone=招录单位咨询电话表


@dataclass
class DiscoverStats:
    pages_visited: int = 0
    attachments: List[Attachment] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    filtered: int = 0        # 命中"是 Excel 但不是公务员职位表"（如事业单位岗位表）而过滤掉的数量
    timeout_hit: bool = False  # 是否因时间预算用完而提前停止


def guess_year(*texts: str) -> Optional[int]:
    """从标题/文件名中识别年度：优先"2026年度""2026年"等表述"""
    for t in texts:
        if not t:
            continue
        m = re.search(r"(20\d{2})\s*(?:年度|年)", t)
        if m:
            return int(m.group(1))
    for t in texts:
        if not t:
            continue
        m = re.search(r"(20\d{2})", t)
        if m:
            return int(m.group(1))
    return None


def extract_links(html: str, base_url: str) -> List[Tuple[str, str]]:
    """极简 HTML 链接抽取（不引入 bs4 依赖）：返回 [(绝对URL, 锚文本)]"""
    out: List[Tuple[str, str]] = []
    for m in re.finditer(r"<a\b[^>]*href\s*=\s*[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", html, re.I | re.S):
        href, inner = m.group(1).strip(), m.group(2)
        title = re.sub(r"<[^>]+>", "", inner)
        title = re.sub(r"\s+", " ", title).strip()
        if not href or href.lower().startswith(("javascript:", "mailto:", "#")):
            continue
        out.append((urljoin(base_url, href), title))
    return out


def extract_page_title(html: str) -> str:
    """取 <title> 作为附件的上下文（很多附件锚文本只有"附件1"，含义在页面标题里）"""
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    if not m:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", m.group(1))).strip()


def is_excel_attachment(url: str, title: str, page_title: str = "") -> bool:
    """
    判断某个链接是否是"公务员职位表"附件。

    ⚠ 实测教训：只按"岗位表/职位表"匹配会把**事业单位公开招聘**的岗位表也抓进来
    （南京、宿迁的市属事业单位岗位表就命中过）。这类不是国考/江苏省考公务员职位，
    必须靠负面词 + 必须命中"公务员/考试录用"来排除。
    """
    low = url.lower().split("?")[0]
    is_file = low.endswith(EXCEL_EXT) or low.endswith(ARCHIVE_EXT)
    # 部分政府站点的下载链接形如 downfile.jsp?filename=xx.xlsx
    if not is_file and re.search(r"\.(xlsx?|zip|rar)(\b|$)", url, re.I):
        is_file = True
    if not is_file:
        return False

    context = " ".join([title, page_title, url])
    # 1) 排除明显不是公务员职位表的（事业单位/编外/劳务派遣/辅警等）
    if any(bad in context for bad in ATTACH_BLOCKLIST):
        return False
    # 2) 必须是公务员相关：标题里出现"公务员"或"考试录用"
    if not any(good in context for good in ATTACH_REQUIRE):
        return False
    # 3) 再要求是职位表类附件
    return any(k in context for k in ATTACH_KEYWORDS) or low.endswith(EXCEL_EXT)


def is_phone_attachment(url: str, title: str, page_title: str = "") -> bool:
    """
    是否是"招录单位咨询电话"附件（zip / docx / xls 都算）。

    实测江苏把它打包成 zip 放在专题页，里面是 13 市 + 省直 + 垂管系统的 Word 电话表；
    文件名形如「江苏省2026年度考试录用公务员招录机关（单位）电话.zip」。
    这类附件不产生职位，只用于给职位回填咨询电话。
    """
    low = url.lower().split("?")[0]
    is_file = (low.endswith(EXCEL_EXT + ARCHIVE_EXT + (".docx", ".doc"))
               or bool(re.search(r"\.(xlsx?|zip|rar|docx?)(\b|$)", url, re.I)))
    if not is_file:
        return False
    context = " ".join([title, page_title, url])
    if "电话" not in context:
        return False
    if any(bad in context for bad in ATTACH_BLOCKLIST):
        return False
    return any(good in context for good in ATTACH_REQUIRE)


def discover_guokao_api(sess: PoliteSession) -> Tuple[List[Attachment], Dict[str, str]]:
    """
    国考官方附件通道（**这是国考唯一可自动化的官方入口**）。

    实测背景：国考专题站是纯 JS 应用（页面 2~4KB、0 链接），静态发现拿不到任何附件；
    但它的常量脚本里写着真正的数据接口，据此可以拿到官方"相关下载"列表：

        GET http://dl.scs.gov.cn/pp/gkweb/core/web/ui/js/core/core-constant.js
            → neu.hb01Id="8a81f6d9..."（本年度专题 id）、neu.aae001="2026"（年度）、
              neu.cdnServer="http://dl.scs.gov.cn"、neu.downloadServer=".../download/"
        GET {cdnServer}/api/res/{hb01Id}/1110
            → {"resList":[{"resourceName":"中央机关及其直属机构2026年度考试录用公务员招考简章.zip",
                           "resResourceId":"8a81f6d1..."}]}
        GET {downloadServer}{resResourceId}  → 官方原件（招考简章/职位表）

    好处：年度 id 由官方脚本给出，**每年换专题时会自动跟着变**，不需要改代码。
    返回 (附件列表, 元信息)
    """
    meta: Dict[str, str] = {}
    js = sess.get_text(GUOKAO_API_JS)
    if not js:
        return [], meta

    def pick(key: str) -> str:
        m = re.search(key + r'\s*[:=]\s*"([^"]*)"', js)
        return m.group(1) if m else ""

    hb01 = pick("hb01Id")
    if not hb01:
        # 官方脚本里它是三元表达式：neu.hb01Id=neu.examSelect?"":"8a81f6d9..."（16+ 位十六进制）
        m = re.search(r'hb01Id\s*[:=][^,;]*?"([0-9a-fA-F]{16,})"', js)
        hb01 = m.group(1) if m else ""
    meta["year"] = pick("aae001")
    meta["topic"] = pick("ahb010")
    cdn = pick("cdnServer") or "http://dl.scs.gov.cn"
    dl_server = pick("downloadServer") or (cdn.rstrip("/") + "/download/")
    if not hb01:
        log.info("  国考接口：常量脚本里没找到 hb01Id（专题可能改版）")
        return [], meta

    raw = sess.get_text("%s/api/res/%s/1110" % (cdn.rstrip("/"), hb01))
    if not raw:
        log.info("  国考接口：%s/api/res/%s/1110 无响应", cdn, hb01)
        return [], meta
    try:
        payload = json.loads(raw)
    except ValueError:
        log.warning("  国考接口：返回的不是 JSON（前 80 字：%s）", raw[:80])
        return [], meta

    try:
        year = int(meta.get("year") or 0) or None
    except ValueError:
        year = None

    atts: List[Attachment] = []
    for item in payload.get("resList") or []:
        name = unquote(str(item.get("resourceName") or ""))
        rid = str(item.get("resResourceId") or "")
        if not name or not rid:
            continue
        # 只要职位表类（招考简章 = 全量职位表原件）；排除面试名单/登记表/推荐表
        if not ("招考简章" in name or "职位表" in name):
            continue
        if any(bad in name for bad in ("人员名单", "登记表", "推荐表", "面试")):
            continue
        atts.append(Attachment(
            url=dl_server.rstrip("/") + "/" + rid,
            title=name,
            page_url=GUOKAO_DOWNLOAD_PAGE,
            source_name="国家公务员局·相关下载（官方接口）",
            exam_type="国考",
            year=year,
            kind="jobs",
        ))
    return atts, meta


def discover_attachments(sess: PoliteSession, src: Source, max_pages: int = 40,
                         deadline: Optional[float] = None) -> DiscoverStats:
    """
    两级跟进：入口页 -> （含"职位表/招录公告"的公告页）-> 附件
    对每个数据源独立 try/except，单个源失败不影响其他源。

    deadline：绝对时间戳（time.time() 口径）。超过就停止继续翻页——
    境外网络访问国内政府站点常常是"连接挂起 30 秒"，没有预算控制会一直跑到任务超时。
    """
    stats = DiscoverStats()
    queue: List[Tuple[str, int]] = [(u, 1) for u in src.entry_pages]
    visited: set = set()

    while queue and stats.pages_visited < max_pages:
        if deadline and time.time() > deadline:
            log.warning("  已用完本次抓取时间预算，停止继续翻页：%s", src.name)
            stats.timeout_hit = True
            break
        url, depth = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)
        host = urlparse(url).netloc
        if host not in src.allowed_hosts:
            continue

        html = sess.get_text(url)
        stats.pages_visited += 1
        if not html:
            stats.errors.append("打开失败：%s" % url)
            continue

        page_title = extract_page_title(html)
        for abs_url, title in extract_links(html, url):
            # 1) 招录单位咨询电话表（不产生职位，用于回填电话）
            if is_phone_attachment(abs_url, title, page_title):
                year = guess_year(title, abs_url, url, page_title)
                stats.attachments.append(Attachment(
                    url=abs_url, title=title or os.path.basename(abs_url),
                    page_url=url, source_name=src.name,
                    exam_type=src.exam_type, year=year or src.year, kind="phone",
                ))
                continue
            # 2) 直接命中职位表附件（用锚文本 + 页面标题 + URL 一起判断）
            if is_excel_attachment(abs_url, title, page_title):
                year = guess_year(title, abs_url, url, page_title)
                stats.attachments.append(Attachment(
                    url=abs_url, title=title or os.path.basename(abs_url),
                    page_url=url, source_name=src.name,
                    exam_type=src.exam_type, year=year or src.year, kind="jobs",
                ))
                continue
            # 记录被过滤掉的 Excel 附件（便于人工确认过滤是否过严）
            low = abs_url.lower().split("?")[0]
            if low.endswith(EXCEL_EXT + ARCHIVE_EXT):
                stats.filtered += 1
                log.debug("  过滤非公务员附件：%s | 页面：%s", (title or abs_url)[:50], page_title[:50])
            # 2) 继续跟进公告页（仅同域名、且标题含关键词）
            if depth < src.depth and urlparse(abs_url).netloc in src.allowed_hosts:
                if any(k in title for k in src.link_keywords) and len(visited) + len(queue) < max_pages:
                    queue.append((abs_url, depth + 1))
        time.sleep(0.5)   # 每个页面之间再喘口气

    # 去重（同一附件可能被多个页面/多个协议链接）。键必须带上 filename= 参数，见 attachment_key()
    seen, uniq = set(), []
    for a in stats.attachments:
        key = attachment_key(a.url)
        if key not in seen:
            seen.add(key)
            uniq.append(a)
    stats.attachments = uniq
    return stats


def attachment_key(url: str) -> str:
    """
    附件去重键。

    ⚠ 踩过的坑：不能简单用 url.split("?")[0] —— 政府站大量附件都是
    `module/download/downfile.jsp?classid=0&filename=xxx.zip` 这种形式，
    去掉查询串后**所有附件的键都相同**，后发现的会被当成重复项丢掉。
    江苏省考"各地职位表.zip"（13 个设区市、约 5800 个职位）就是这样被
    "招录机关电话.zip"挤掉的，导致自动抓取只拿到省直+垂管的 338 条。
    这里优先用 filename= 参数做键，并把 http/https 视为同一文件。
    """
    p = urlparse(url)
    m = re.search(r"filename=([^&]+)", p.query)
    if m:
        return "file:" + unquote(m.group(1)).lower()
    return (p.netloc + p.path).lower()


# =========================================================================== #
#                        三、下载与解压
# =========================================================================== #

PHONE_EXT = (".docx", ".doc", ".pdf")

# 国考官方附件通道（专题站是 JS 应用，只能走它自己的数据接口）
GUOKAO_API_JS = "http://dl.scs.gov.cn/pp/gkweb/core/web/ui/js/core/core-constant.js"
GUOKAO_DOWNLOAD_PAGE = "http://bm.scs.gov.cn/pp/gkweb/core/web/ui/business/download/gkdownloads.html"


def safe_filename(url: str, title: str) -> str:
    """
    生成安全的本地文件名。政府站的下载链接常是 downfile.jsp?classid=0&filename=xxx.zip，
    必须优先取 filename= 参数里的真实文件名（否则扩展名判断会全错，.zip/.docx 会被当成 .xlsx）。

    实测教训：国考官方附件形如 http://dl.scs.gov.cn/download/<资源id>，**URL 里根本没有文件名**，
    这时要退回用锚文本/资源名里的真实文件名（如「…招考简章.zip」），否则会被当成 .xlsx，
    导致压缩包被当作 Excel 去解析而失败。
    """
    query = urlparse(url).query
    m = re.search(r"filename=([^&]+)", query)
    raw = unquote(m.group(1)) if m else (os.path.basename(urlparse(url).path) or "attachment")
    low = os.path.splitext(raw)[1].lower()
    if low not in EXCEL_EXT + ARCHIVE_EXT + PHONE_EXT:
        # URL 里没有可用扩展名 -> 从标题/资源名里找真实文件名
        m2 = re.search(r'([^\\/:*?"<>|\s]+\.(?:xlsx?|xlsm|zip|rar|7z|docx?|pdf))', title or "", re.I)
        if m2:
            raw = m2.group(1)
    base = re.sub(r"[\\/:*?\"<>|\s]+", "_", raw)[:80] or "attachment"
    ext = os.path.splitext(base)[1].lower()
    if ext not in EXCEL_EXT + ARCHIVE_EXT + PHONE_EXT:
        base = re.sub(r"\.(jsp|do|action|html?)$", "", base, flags=re.I) + ".xlsx"
    digest = hashlib.md5(url.encode("utf-8")).hexdigest()[:8]
    return "%s_%s" % (digest, base)


def download_attachment(sess: PoliteSession, att: Attachment, out_dir: str) -> List[str]:
    """下载附件并（必要时）解压，返回本地 Excel 文件路径列表"""
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, safe_filename(att.url, att.title))
    if os.path.exists(path) and os.path.getsize(path) > 0:
        log.info("  已存在，跳过下载：%s", os.path.basename(path))
    else:
        content = sess.get_bytes(att.url)
        if not content:
            return []
        if len(content) < 1024:
            log.warning("  附件过小（%d 字节），可能是错误页，跳过：%s", len(content), att.url)
            return []
        with open(path, "wb") as fh:
            fh.write(content)

    low = path.lower()
    # 按"内容特征"判断，而不是只看扩展名：
    #   .xlsx 本身也是 zip（含 xl/ 目录），必须与"装着 Excel 的压缩包"区分开
    if zipfile.is_zipfile(path):
        try:
            with zipfile.ZipFile(path) as zf:
                names = zf.namelist()
        except zipfile.BadZipFile:
            names = []
        excel_entries = [n for n in names if n.lower().endswith(EXCEL_EXT)]
        is_xlsx_itself = any(n.startswith("xl/") for n in names)
        if is_xlsx_itself and not any(n.lower().endswith(".xls") for n in excel_entries):
            return [path]                      # 它自己就是 xlsx
        if excel_entries:
            return unzip_excel(path, out_dir)  # 是压缩包，解出里面的 Excel
        log.warning("  压缩包里没有 Excel：%s（%s）", os.path.basename(path), names[:4])
        return []
    if low.endswith(EXCEL_EXT):
        return [path]
    if low.endswith((".rar", ".7z")):
        log.warning("  .rar/.7z 需外部工具解压，已跳过：%s（请在本地解压后用 --local 传入）", path)
        return []
    log.warning("  无法识别的附件类型：%s", os.path.basename(path))
    return []


def download_and_parse_phone(sess: PoliteSession, att: Attachment) -> List[Tuple[str, str, str]]:
    """
    下载"招录单位咨询电话"附件并解析成 [(地区, 单位, 电话)]。
    支持：zip（内含 docx/xls）· docx · xls/xlsx；旧版 .doc 需人工另存为 .docx。
    """
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    path = os.path.join(DOWNLOAD_DIR, safe_filename(att.url, att.title))
    if not (os.path.exists(path) and os.path.getsize(path) > 0):
        content = sess.get_bytes(att.url)
        if not content:
            return []
        if len(content) < 512:
            log.warning("  电话附件过小（%d 字节），跳过：%s", len(content), att.url)
            return []
        with open(path, "wb") as fh:
            fh.write(content)

    entries: List[Tuple[str, str, str]] = []
    low = path.lower()
    if low.endswith((".zip", ".rar", ".7z")):
        for doc in extract_docs_from_archive(path):
            entries.extend(parse_phone_table(doc))
    else:
        entries.extend(parse_phone_table(path))
    return entries


def unzip_excel(zip_path: str, out_dir: str) -> List[str]:
    """解压 zip，返回其中的 Excel 文件路径（忽略 __MACOSX 等垃圾）"""
    results: List[str] = []
    target = os.path.splitext(zip_path)[0] + "_unzip"
    try:
        with zipfile.ZipFile(zip_path) as zf:
            for info in zf.infolist():
                name = info.filename
                if name.startswith("__MACOSX") or name.endswith("/"):
                    continue
                if not name.lower().endswith(EXCEL_EXT):
                    continue
                # 只取看起来像职位表的文件
                if not (any(k in name for k in ATTACH_KEYWORDS) or len(zf.namelist()) <= 3):
                    continue
                os.makedirs(target, exist_ok=True)
                out = os.path.join(target, os.path.basename(name))
                with zf.open(info) as src_fh, open(out, "wb") as dst_fh:
                    dst_fh.write(src_fh.read())
                results.append(out)
    except zipfile.BadZipFile:
        log.warning("  zip 文件损坏：%s", zip_path)
    return results


def extract_docs_from_archive(path: str) -> List[str]:
    """
    从压缩包里解出"招录单位咨询电话"文档（.docx/.doc/.xls*）。
    实测江苏省人社厅把电话表打包成 zip，里面是 13 市 + 省直 + 垂管系统的 Word 文档。
    """
    out_dir = os.path.splitext(path)[0] + "_phone"
    results: List[str] = []
    try:
        with zipfile.ZipFile(path) as zf:
            for info in zf.infolist():
                name = info.filename
                if name.startswith("__MACOSX") or name.endswith("/"):
                    continue
                if not name.lower().endswith((".docx", ".doc", ".xls", ".xlsx", ".xlsm")):
                    continue
                os.makedirs(out_dir, exist_ok=True)
                out = os.path.join(out_dir, os.path.basename(name))
                with zf.open(info) as src_fh, open(out, "wb") as dst_fh:
                    dst_fh.write(src_fh.read())
                results.append(out)
    except zipfile.BadZipFile:
        log.warning("  压缩包不是 zip 或已损坏：%s（.rar 请先手动解压）", os.path.basename(path))
    if results:
        log.info("  电话压缩包 %s -> 解出 %d 个文档", os.path.basename(path), len(results))
    return results


# =========================================================================== #
#                   四、Excel 解析与字段归一化
# =========================================================================== #

def _norm_header(v) -> str:
    """表头归一化：去掉空白（含全角空格）便于匹配"""
    return re.sub(r"[\s\u3000]+", "", clean_text(v))


def find_header_row(raw: "pd.DataFrame", max_scan: int = 12) -> Optional[int]:
    """
    在"未设表头"的工作表里找出真正的表头行。

    为什么需要：官方职位表第一行常常是**合并的大标题**（如"2026年度盐城市考录职位简介表"），
    有时前面还有一个空行，直接 header=0 会把标题当表头，导致所有列名变成 Unnamed。
    做法：逐行打分——命中已知表头别名的单元格越多分越高，取最高分且 >=3 分的行。
    """
    all_aliases = [a for alist in COLUMN_ALIASES.values() for a in alist if a]
    best_idx, best_score = None, 0
    for i in range(min(max_scan, len(raw))):
        score = 0
        for cell in raw.iloc[i].tolist():
            c = _norm_header(cell)
            if not c or c.lower() == "nan":
                continue
            if c in all_aliases:
                score += 2
            elif any(a in c for a in all_aliases if len(a) >= 2):
                score += 1
        if score > best_score:
            best_idx, best_score = i, score
    return best_idx if best_score >= 3 else None


def read_excel_all_sheets(path: str) -> "pd.DataFrame":
    """
    读取 Excel 的全部 sheet 并纵向合并。

    国考职位表通常 4 个 sheet（中央党群/国家行政机关直属机构/参照公务员法管理事业单位/…），
    江苏省考职位表按地市分 sheet，都必须合并。
    表头行通过 find_header_row 自动识别（真实表里第一行往往是合并标题，甚至先有一个空行）。
    """
    ext = os.path.splitext(path)[1].lower()
    engines: List[Optional[str]]
    if ext in (".xlsx", ".xlsm"):
        engines = ["openpyxl", None]
    else:  # .xls
        engines = ["xlrd", "openpyxl", None]

    last_err: Optional[Exception] = None
    for engine in engines:
        try:
            sheets = pd.read_excel(path, sheet_name=None, dtype=str, header=None, engine=engine)
            frames = []
            for name, raw in sheets.items():
                if raw is None or raw.empty:
                    continue
                raw = raw.dropna(how="all").dropna(axis=1, how="all")
                if raw.empty or raw.shape[1] < 2:
                    continue
                hidx = find_header_row(raw)
                if hidx is None:
                    log.warning("  工作表「%s」未识别到表头行，已跳过（可用 --verbose 查看前几行）", name)
                    continue
                header = [clean_text(x) for x in raw.iloc[hidx].tolist()]
                body = raw.iloc[hidx + 1:].copy()
                body.columns = header
                # 去掉与表头重复的行（多 sheet 合并后常见）与全空行
                body = body[~body.apply(
                    lambda r: all(_norm_header(v) == _norm_header(h) for v, h in zip(r.tolist(), header)),
                    axis=1)]
                body = body.dropna(how="all")
                # 去掉重名列，避免 pandas 取列时返回 DataFrame（历史 bug）
                body = body.loc[:, ~body.columns.duplicated()]
                body["_sheet"] = name
                log.debug("  工作表「%s」表头行=%d，数据 %d 行，列=%s",
                          name, hidx, len(body), list(body.columns)[:14])
                frames.append(body)
            if frames:
                return pd.concat(frames, ignore_index=True, sort=False)
        except Exception as exc:      # 换下一个引擎再试
            last_err = exc
            continue
    raise RuntimeError("无法解析 Excel：%s（%s）" % (path, last_err))


def build_column_map(df: "pd.DataFrame") -> Dict[str, str]:
    """
    建立 {标准字段: 原始列名} 的映射。

    注意：**绝不能**用 df.rename() 直接改名 —— 官方职位表里常有
    「职位简介」和「备注」同时存在的情况，若两列都被映射成同一个标准名，
    pandas 会出现重名列，后续 row["备注"] 取到的将是一个 Series 而非字符串
    （历史 bug）。这里改为"标准字段 -> 唯一原始列"的取值方式，从根上避免重名。

    匹配策略：先精确匹配表头，再做包含匹配兜底。
    """
    raw_cols: List[Tuple[object, str]] = [
        (c, str(c).strip().replace(" ", "").replace("\u3000", "")) for c in df.columns
    ]
    std2raw: Dict[str, str] = {}
    used_raw: set = set()

    # 1) 精确匹配优先，保证「备注」映射到「备注」而不是「职位简介」
    for std, aliases in COLUMN_ALIASES.items():
        for raw, norm in raw_cols:
            if raw in used_raw:
                continue
            if norm in aliases:
                std2raw[std] = raw
                used_raw.add(raw)
                break
    # 2) 包含匹配兜底（只补充尚未映射到的标准字段）
    for std, aliases in COLUMN_ALIASES.items():
        if std in std2raw:
            continue
        for raw, norm in raw_cols:
            if raw in used_raw:
                continue
            if any(a and a in norm for a in aliases):
                std2raw[std] = raw
                used_raw.add(raw)
                break
    return std2raw


def clean_text(v) -> str:
    """去除多余空白、全角空格、换行，统一为单行文本"""
    if v is None:
        return ""
    try:
        if v != v:            # NaN
            return ""
    except Exception:
        pass
    s = str(v)
    s = s.replace("\u3000", " ").replace("\xa0", " ")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


# ------------------------------ 专业匹配 ------------------------------ #

RE_NO_LIMIT = re.compile(r"不限专业|专业不限|不作专业限制|无专业限制|专业无限制|^不限$|^专业?不限$|^无限制$")
RE_BIO_SCI_EXACT = re.compile(r"生物科学(?!类)")          # "生物科学"但排除"生物科学类"
RE_BIO_SCI_CLASS = re.compile(r"生物科学类")
RE_BASIC_SCIENCE = re.compile(r"基础理学类|理学类")
RE_EDU_CLASS = re.compile(r"教育类|教育学类|学科教学|师范类")
RE_BIO_OTHER = re.compile(r"生物|生命科学|生物工程|生物技术|生态")


def tag_majors(major_text: str) -> List[str]:
    """
    按专业要求原文打标签（与前端 index.html 中的 inferMajorTags 规则一致）。
    标签取值：生物科学 / 生物科学类 / 基础理学类 / 教育类 / 不限专业 / 相近专业
    """
    t = clean_text(major_text)
    if not t:
        return []
    if RE_NO_LIMIT.search(t):
        return ["不限专业"]

    tags: List[str] = []
    if RE_BIO_SCI_EXACT.search(t):
        tags.append("生物科学")
    if RE_BIO_SCI_CLASS.search(t):
        tags.append("生物科学类")
    if RE_BASIC_SCIENCE.search(t):
        tags.append("基础理学类")
    if RE_EDU_CLASS.search(t):
        tags.append("教育类")
    if "生物科学" not in tags and "生物科学类" not in tags and RE_BIO_OTHER.search(t):
        tags.append("相近专业")
    # 去重且保持稳定顺序
    return [t_ for i, t_ in enumerate(tags) if t_ not in tags[:i]]


# ------------------------------ 其他字段推导 ------------------------------ #

RE_TEACHER_CERT = re.compile(r"教师资格|教师资格证|教师证")
RE_NORMAL_MAJOR = re.compile(r"师范类|师范专业|须为师范|限师范")
RE_YINGJIE = re.compile(r"应届")
RE_ZEYEQI = re.compile(r"择业期")
RE_WANGSHOU = re.compile(r"往届|社会人员|在职人员|非应届")
RE_NO_LIMIT_ID = re.compile(r"不限|均可|无限制")


def derive_identity(row_text: str) -> str:
    """身份要求：职位表常常没有单独一列，需要从备注/职位简介中推导"""
    t = clean_text(row_text)
    if not t:
        return "不限"
    if RE_ZEYEQI.search(t):
        return "应届/择业期内"
    if RE_YINGJIE.search(t):
        return "应届"
    if RE_WANGSHOU.search(t):
        return "往届"
    return "不限"


# ---- 江苏省考职位表没有"政治面貌/基层年限/户籍"列，要求都写在「其它」里，这里补出来 ----

def derive_political(current: str, remark: str) -> str:
    if current and current != "不限":
        return current
    if re.search(r"政治面貌不限|不限政治面貌", remark):
        return "不限"
    tags = []
    if re.search(r"中共党员|党员", remark):
        tags.append("中共党员")
    if re.search(r"共青团员|团员", remark):
        tags.append("共青团员")
    if re.search(r"群众", remark):
        tags.append("群众")
    return "或".join(tags) if tags else (current or "不限")


_YEAR_TEXT = {"一": "满1年", "1": "满1年", "两": "满2年", "二": "满2年", "2": "满2年",
              "三": "满3年", "3": "满3年"}


def derive_experience(current: str, remark: str) -> str:
    if current and current not in ("无", "不限", ""):
        return current
    m = (re.search(r"(一|1|两|二|2|三|3)\s*年(?:以上)?(?:的)?基层工作经历", remark)
         or re.search(r"基层工作经历[^，,；;。]{0,12}?(一|1|两|二|2|三|3)\s*年", remark))
    if m:
        return _YEAR_TEXT.get(m.group(1), "无")
    if "基层工作经历" in remark:
        return "有要求（详见其他条件）"
    return current or "无"


def derive_hukou(current: str, remark: str) -> str:
    if current:
        return current
    m = re.search(r"[^，,；;。]{0,24}(?:户籍|生源)[^，,；;。]{0,24}", remark)
    return m.group(0).strip() if m else "不限"


# 江苏省考用"职位代码"的后两位表示招录对象，这是判断"能不能报"的关键信息：
#   60-69 面向应届毕业生 | 70-79 法官/检察官助理 | 80-81 面向残疾人
#   90-96 面向服务基层项目人员 | 98 面向优秀村（社区）书记主任
TARGETED_CODES = {
    "70": "法官助理", "71": "法官助理", "72": "法官助理", "73": "法官助理", "74": "法官助理",
    "75": "检察官助理", "76": "检察官助理", "77": "检察官助理", "78": "检察官助理", "79": "检察官助理",
    "80": "面向残疾人", "81": "面向残疾人",
    "90": "服务基层项目人员", "91": "服务基层项目人员", "92": "服务基层项目人员",
    "93": "服务基层项目人员", "94": "服务基层项目人员", "95": "服务基层项目人员",
    "96": "服务基层项目人员", "98": "优秀村（社区）书记主任",
}


def identity_by_code(code: str, current: str) -> str:
    """用职位代码后两位判断招录对象（江苏省考特有），国考的 12 位代码不会命中"""
    c = clean_text(code)
    if not c.isdigit() or len(c) > 3:
        return current
    tail = c.zfill(2)
    if tail in TARGETED_CODES:
        return "定向岗位·" + TARGETED_CODES[tail]
    if "60" <= tail <= "69":
        return "应届"
    return current


def is_targeted(job: Dict[str, object]) -> bool:
    """是否属于"定向招录"（本科应届一般报不了，默认排除）"""
    if "定向岗位" in clean_text(job.get("身份要求")):
        return True
    tail = clean_text(job.get("职位代码")).zfill(2)
    return tail in TARGETED_CODES


def derive_exam_year(exam_type: str, year: Optional[int], title: str = "") -> int:
    y = year or guess_year(title)
    if y:
        return y
    # 兜底：江苏省考通常在上一年的 10-11 月发布，国考同理
    now = datetime.now(CST)
    return now.year + 1 if now.month >= 9 else now.year


def classify(job: Dict[str, object]) -> Tuple[str, str, str]:
    """
    匹配结论（与前端 index.html 的 classify 规则完全一致）
      返回 (等级, 说明, 是否需电话咨询)
      A 完全匹配 / B 可能匹配需核实 / C 不限专业 / D 条件不符但相近
    """
    major_text = clean_text(job.get("专业要求原文"))
    tags = job.get("专业目录归属") or tag_majors(major_text)
    if not isinstance(tags, list):
        tags = tag_majors(str(tags))
    edu = clean_text(job.get("学历要求"))
    extra = " ".join([clean_text(job.get("其他条件")), clean_text(job.get("备注"))])

    need_cert = bool(RE_TEACHER_CERT.search(extra) or RE_TEACHER_CERT.search(major_text))
    need_normal = bool(RE_NORMAL_MAJOR.search(extra) or RE_NORMAL_MAJOR.search(major_text))
    reasons: List[str] = []

    bachelor_ok = (edu == "") or bool(re.search(r"不限|本科|大专|专科", edu)) or not re.search(r"研究生|硕士|博士", edu)

    if not bachelor_ok:
        level, reasons = "D", ["学历要求为%s，本科不可报或需进一步确认" % (edu or "未注明")]
    elif "不限专业" in tags:
        level, reasons = "C", ["专业不限，任何专业均可报考"]
    else:
        exact = "生物科学" in tags
        broad = ("生物科学类" in tags) or ("基础理学类" in tags)
        edu_cls = "教育类" in tags
        if exact or broad:
            if need_normal or need_cert:
                level = "B"
                extra_req = "、".join([x for x in ["师范类" if need_normal else "", "教师资格证" if need_cert else ""] if x])
                reasons = ["专业目录匹配，但岗位额外要求" + extra_req]
            else:
                level = "A"
                matched = "生物科学" if exact else "、".join([t for t in tags if t in ("生物科学类", "基础理学类")])
                reasons = ["专业目录明确包含" + matched]
        elif edu_cls:
            level, reasons = "B", ["属于教育类/师范方向，需核对本科专业是否被认定为教育类"]
        else:
            level, reasons = "D", ["专业要求未明确包含生物科学相关目录，仅条件相近，需电话核实"]

    # 是否需电话咨询招录单位
    call_reasons: List[str] = []
    if "师范" in major_text:
        call_reasons.append("毕业证专业名称含「师范」，各省专业目录认定口径不同")
    if need_normal:
        call_reasons.append("岗位要求师范类")
    if need_cert:
        call_reasons.append("岗位要求教师资格证")
    if level != "A":
        call_reasons.append("匹配结论非完全匹配")
    return level, "；".join(reasons), "；".join(call_reasons) if call_reasons else "否"


# --------------------------- 咨询电话（Word 电话表） --------------------------- #

REGION_FILE = os.path.join(BASE_DIR, "jiangsu_regions.json")


def load_region_map() -> Dict[str, str]:
    """江苏 区县/县级市 -> 设区市 映射（与前端 index.html 共用同一份 jiangsu_regions.json）"""
    try:
        with open(REGION_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as exc:
        log.warning("  读取 %s 失败：%s", REGION_FILE, exc)
        return {}
    mapping: Dict[str, str] = {}
    for city, names in data.items():
        if city.startswith("_"):
            continue
        for n in names:
            mapping[clean_text(n)] = city
        mapping[city] = city
    return mapping


def _norm_unit(s: str) -> str:
    """单位名归一化：去空白/全角空格（电话表里常写成"单 位 名 称"）"""
    return re.sub(r"[\s\u3000]+", "", clean_text(s))


def parse_phone_table(path: str) -> List[Tuple[str, str, str]]:
    """
    解析"招录单位咨询电话"表，返回 [(地区名称, 单位名称, 咨询电话)]。

    实测两种排版都要支持：
      · 各市：序号 | 地区名称 | 单位名称 | 咨询电话      （4 列）
      · 省直：序号 | 单 位 名 称 | 报名咨询电话          （3 列）
    .docx 用 python-docx；.xls/.xlsx 走 pandas（未来的年份可能直接给 Excel）。
    """
    rows: List[Tuple[str, str, str]] = []
    low = path.lower()

    if low.endswith((".xls", ".xlsx", ".xlsm")):
        try:
            df = read_excel_all_sheets(path)
        except Exception as exc:
            log.warning("  电话表解析失败 %s：%s", os.path.basename(path), exc)
            return rows
        cols = list(df.columns)
        unit_col = next((c for c in cols if "单位名称" in _norm_unit(str(c)) or _norm_unit(str(c)) == "单位"), None)
        phone_col = next((c for c in cols if "电话" in str(c)), None)
        city_col = next((c for c in cols if "地区" in str(c) or "城市" in str(c)), None)
        if unit_col and phone_col:
            for _, r in df.iterrows():
                rows.append((clean_text(r.get(city_col)) if city_col else "",
                             _norm_unit(r.get(unit_col)), clean_text(r.get(phone_col))))
        return rows

    if not low.endswith(".docx"):
        log.warning("  电话表暂只支持 .docx/.xls（旧版 .doc 请先另存为 .docx）：%s", os.path.basename(path))
        return rows

    try:
        from docx import Document      # python-docx
    except ImportError:
        log.warning("  未安装 python-docx，无法解析电话表（pip install python-docx）")
        return rows

    try:
        doc = Document(path)
    except Exception as exc:
        log.warning("  电话表打开失败 %s：%s", os.path.basename(path), exc)
        return rows

    for table in doc.tables:
        for row in table.rows:
            raw = [clean_text(c.text) for c in row.cells]
            cells = [_norm_unit(t) for t in raw]
            if len(cells) < 3:
                continue
            # 表头行跳过
            if any("单位名称" in c or "咨询电话" in c or "报名咨询" in c for c in cells):
                continue
            # 电话单元格里可能有两行号码（如"0514-86556792\n0514-86299302"），用 / 分开而不是粘在一起
            phone = ""
            for t in reversed(raw):
                if re.search(r"\d{3,}", t):
                    phone = re.sub(r"\s*[\r\n\u3000]+\s*", " / ", t).strip()
                    break
            if not phone:
                continue
            unit = cells[2] if len(cells) >= 4 else cells[1]
            city = cells[1] if len(cells) >= 4 else ""
            if not unit or unit.isdigit():
                continue
            rows.append((city, unit, phone))
    return rows


def build_phone_index(entries: List[Tuple[str, str, str]], regions: Dict[str, str]) -> Dict[str, str]:
    """
    构建电话索引。键有三种，按优先级查找：
       ① "设区市|单位名"   ② "|单位名"（唯一时）   ③ 单位名本身
    """
    index: Dict[str, str] = {}
    unit_counts: Dict[str, int] = {}
    for city, unit, phone in entries:
        city_key = regions.get(city, city) if city else ""
        if city_key:
            index["%s|%s" % (city_key, unit)] = phone
        unit_counts[unit] = unit_counts.get(unit, 0) + 1
        index.setdefault("|%s" % unit, phone)
    for unit, n in unit_counts.items():
        if n == 1:
            index[unit] = index["|%s" % unit]
    return index


def lookup_phone(index: Dict[str, str], unit: str, place: str, regions: Dict[str, str]) -> str:
    """按 (城市, 单位) 找电话；找不到退化为单位名匹配；再退化用包含匹配"""
    if not index or not unit:
        return ""
    u = _norm_unit(unit)
    city = regions.get(clean_text(place), clean_text(place))
    for key in ("%s|%s" % (city, u), "|%s" % u, u):
        if key in index:
            return index[key]
    short = re.sub(r"^(省|市|区|县)", "", u)
    if short:
        for key in ("%s|%s" % (city, short), "|%s" % short):
            if key in index:
                return index[key]
    return ""


# ------------------------------ 行 -> 职位对象 ------------------------------ #

def rows_to_jobs(df: "pd.DataFrame", *, exam_type: str, year: Optional[int],
                 source_url: str, source_name: str, source_file: str,
                 scraped_at: str,
                 phone_index: Optional[Dict[str, str]] = None,
                 regions: Optional[Dict[str, str]] = None) -> List[Dict[str, object]]:
    colmap = build_column_map(df)          # {标准字段: 原始列名}
    if not colmap:
        log.warning("  表头无法识别，跳过该文件：%s", source_file)
        log.info("  实际表头：%s", list(df.columns)[:20])
        return []
    log.debug("  字段映射：%s", {k: str(v) for k, v in colmap.items()})

    jobs: List[Dict[str, object]] = []

    for _, row in df.iterrows():
        def g(field_name: str) -> str:
            """按标准字段名取值（列名重复时也不会取到 Series）"""
            raw = colmap.get(field_name)
            if raw is None:
                return ""
            val = row.get(raw, "")
            if hasattr(val, "tolist"):        # 兜底：万一遇到重名列返回 Series
                val = next((x for x in val.tolist() if clean_text(x)), "")
            return clean_text(val)

        major_text = g("专业要求原文")
        title = g("职位名称")
        org = g("招录机关")
        unit = g("用人司局/单位")
        if not (title or org or unit):
            continue                    # 空行 / 表头重复行
        if title in ("招考职位", "职位名称", "岗位名称"):
            continue                    # 多 sheet 合并后可能重复表头

        # 备注 + 职位简介 + 其他条件 合并，用于推导身份要求等
        remark = "；".join([x for x in [g("备注"), g("职位简介"), g("其他条件")] if x])
        identity = g("身份要求") or derive_identity(remark + " " + title)
        if re.search(r"不限", g("身份要求")):
            identity = "不限"
        # 江苏省考：用职位代码后两位校正招录对象（定向岗位/应届）
        identity = identity_by_code(g("职位代码"), identity)

        # 咨询电话：表里有就用表里的；没有就从"招录单位咨询电话"文档里按 (城市,单位) 匹配
        place = g("工作地点") or ("江苏省" if "江苏" in exam_type else "")
        phone = g("咨询电话")
        if not phone and phone_index:
            phone = lookup_phone(phone_index, org or unit, place, regions or {})

        job: Dict[str, object] = {
            "考试类型": exam_type,
            "年度": derive_exam_year(exam_type, year, source_file),
            "职位代码": g("职位代码"),
            "招录机关": org or unit,
            "用人司局/单位": unit,
            "职位名称": title,
            "招录人数": g("招录人数"),
            "工作地点": place,
            "学历要求": g("学历要求"),
            "学位要求": g("学位要求"),
            "专业要求原文": major_text,
            "专业目录归属": tag_majors(major_text),
            "政治面貌": derive_political(g("政治面貌"), remark),
            "基层工作最低年限": derive_experience(g("基层工作最低年限") or g("服务基层项目工作经历"), remark),
            "身份要求": identity,
            "户籍/生源要求": derive_hukou(g("户籍/生源要求"), remark),
            "其他条件": g("其他条件"),
            "考试类别": g("考试类别"),
            "面试比例": g("面试比例"),
            "备注": g("备注") or g("职位简介"),
            "咨询电话": phone,
            "落户地点": g("落户地点"),
            "机构性质": g("机构性质"),
            "来源链接": source_url,
            "来源文件": source_file,
            "数据来源": source_name,
            "抓取时间": scraped_at,
        }
        level, reason, need_call = classify(job)
        job["匹配结论"] = level
        job["匹配说明"] = reason
        job["需电话咨询"] = need_call
        jobs.append(job)
    return jobs


def is_jiangsu(job: Dict[str, object]) -> bool:
    text = " ".join([clean_text(job.get(k)) for k in ("工作地点", "招录机关", "用人司局/单位")])
    if "江苏省考" in str(job.get("考试类型", "")):
        return True
    return any(k in text for k in JIANGSU_KEYWORDS)


def is_relevant_biology(job: Dict[str, object]) -> bool:
    """是否与"本科·生物科学（师范）"相关（用于默认收窄数据量）"""
    tags = job.get("专业目录归属") or []
    if tags:
        return True
    return bool(RE_BIO_OTHER.search(clean_text(job.get("专业要求原文"))))


# =========================================================================== #
#                        五、主流程
# =========================================================================== #

def load_existing(path: str) -> Tuple[Dict[str, dict], Dict[str, object]]:
    """读取已有 data.json，返回 (以唯一键索引的职位字典, meta)"""
    if not os.path.exists(path):
        return {}, {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except Exception as exc:
        log.warning("已有 data.json 解析失败（%s），将重新生成", exc)
        return {}, {}
    if isinstance(payload, list):
        records, meta = payload, {}
    elif isinstance(payload, dict):
        records, meta = payload.get("jobs", []), payload.get("meta", {})
    else:
        records, meta = [], {}
    index = {job_key(r): r for r in records if isinstance(r, dict)}
    return index, meta


def job_key(job: Dict[str, object]) -> str:
    """
    职位唯一键。
    注意：**国考的职位代码是全局唯一的**（如 300110001001），但**江苏省考是"市内 2 位编号"**
    （如"60"），不同单位会重复，必须叠加招录机关，否则会把上千个职位挤成几十个。
    """
    code = clean_text(job.get("职位代码"))
    org = clean_text(job.get("招录机关")) or clean_text(job.get("用人司局/单位"))
    # 城市必须进键：像"市场监督管理局""街道办事处"这类名称各市都有，光靠 机关+代码 会撞车
    place = clean_text(job.get("工作地点"))
    if code:
        return "|".join([clean_text(job.get("考试类型")), clean_text(job.get("年度")),
                         place, org, code])
    return "|".join([place, org, clean_text(job.get("职位名称")),
                     clean_text(job.get("专业要求原文"))[:40]])


def apply_year_policy(jobs: List[Dict[str, object]], policy: str = "latest"
                      ) -> Tuple[List[Dict[str, object]], Dict[str, int], List[int]]:
    """
    年度策略：latest = 每种考试类型只保留**最新年度**的记录。

    这就是"有新表就替换旧表"：2027 年度的职位表一旦被官方发布并抓到，
    2026 年度的旧记录会被自动丢弃（可用 --year-policy keep-all 保留历年做对比）。
    返回 (保留的记录, 各考试类型的最新年度, 被丢弃的年度列表)
    """
    newest: Dict[str, int] = {}
    for j in jobs:
        et = clean_text(j.get("考试类型")) or "未知"
        try:
            y = int(clean_text(j.get("年度")) or 0)
        except ValueError:
            y = 0
        if y > newest.get(et, 0):
            newest[et] = y
    if policy != "latest":
        return jobs, newest, []

    kept: List[Dict[str, object]] = []
    dropped_years: set = set()
    for j in jobs:
        et = clean_text(j.get("考试类型")) or "未知"
        try:
            y = int(clean_text(j.get("年度")) or 0)
        except ValueError:
            y = 0
        if y >= newest.get(et, 0):
            kept.append(j)
        else:
            dropped_years.add(y)
    return kept, newest, sorted(dropped_years)


def merge_jobs(existing: Dict[str, dict], fresh: List[Dict[str, object]]) -> Tuple[List[Dict[str, object]], int, int]:
    """合并新旧数据：新数据覆盖同唯一键的旧记录，返回 (全部记录, 新增数, 更新数)"""
    merged = dict(existing)
    added = updated = 0
    for job in fresh:
        k = job_key(job)
        if k in merged:
            old = merged[k]
            # 保留旧的抓取时间用于比较，仅在有实质变化时算作"更新"
            if any(clean_text(old.get(f)) != clean_text(job.get(f))
                   for f in ("专业要求原文", "学历要求", "招录人数", "其他条件", "工作地点", "职位名称")):
                updated += 1
            merged[k] = {**old, **job}
        else:
            merged[k] = job
            added += 1
    return list(merged.values()), added, updated


def write_data_json(path: str, jobs: List[Dict[str, object]], meta: Dict[str, object]) -> None:
    payload = {"meta": meta, "jobs": jobs}
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)               # 原子替换，避免写到一半被中断


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="公考职位表抓取/清洗工具：生成前端使用的 data.json（仅使用官方数据）",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--local", nargs="+", metavar="XLSX",
                   help="使用本地已下载的官方职位表（.xlsx/.xls），可传多个文件；"
                        "文件名含「电话」的会被当作招录单位咨询电话表")
    p.add_argument("--phone-file", action="append", default=[], metavar="DOCX",
                   help="招录单位咨询电话表（.docx/.xls，可重复传）；用于补全职位的咨询电话")
    p.add_argument("--exam-type", default="江苏省考",
                   help="配合 --local 使用：数据所属考试类型（默认 江苏省考）")
    p.add_argument("--year", type=int, default=None, help="配合 --local 使用：年度（默认自动识别）")
    p.add_argument("--source-url", default="", help="配合 --local 使用：官方原文链接")
    p.add_argument("--source-name", default="", help="配合 --local 使用：数据来源名称")
    p.add_argument("--output", default=OUTPUT_JSON, help="输出文件路径（默认 ./data.json）")
    p.add_argument("--delay", type=float, default=DEFAULT_DELAY, help="同一域名请求最小间隔秒数（默认 3）")
    p.add_argument("--strict-tls", action="store_true",
                   help="严格校验 HTTPS 证书；默认遇到证书链异常的政府站点会降级重试并记录日志")
    p.add_argument("--max-pages", type=int, default=40, help="每个数据源最多访问的页面数（默认 40）")
    p.add_argument("--time-budget", type=int, default=900,
                   help="本次抓取的总时间预算（秒，默认 900=15 分钟）；到点停止翻页，避免撞上 CI 任务超时")
    p.add_argument("--scope", choices=["jiangsu-biology", "all"], default="jiangsu-biology",
                   help="收录范围：jiangsu-biology=江苏且与生物科学相关（默认）；all=全部")
    p.add_argument("--data-status", choices=["auto", "official", "local-import", "sample"],
                   default="auto", help="写入 meta.data_status 的数据状态标记；sample 会在每条记录上标注「是否示例=true」")
    p.add_argument("--no-merge", action="store_true", help="不合并历史数据，直接用本次抓取结果覆盖")
    p.add_argument("--include-targeted", action="store_true",
                   help="保留定向招录岗位（面向服务基层项目人员/优秀村书记/残疾人/法官检察官助理）；默认排除")
    p.add_argument("--year-policy", choices=["latest", "keep-all"], default="latest",
                   help="latest=每类考试只保留最新年度（实现「有新表就替换旧表」，默认）；keep-all=保留历年")
    p.add_argument("--check-only", action="store_true", help="只检查是否存在新的职位表附件，不下载")
    p.add_argument("--dry-run", action="store_true", help="解析但不写入 data.json")
    p.add_argument("--selftest", action="store_true", help="离线自检解析与匹配逻辑，不联网")
    p.add_argument("--verbose", "-v", action="store_true", help="输出调试日志")
    return p


def setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


# --------------------------------------------------------------------------- #
# 自检：验证"专业打标签 + 匹配结论"，不联网
# --------------------------------------------------------------------------- #
def selftest() -> int:
    cases = [
        ("生物科学（师范）",           "本科及以上", "研究生", "A"),
        ("生物科学类、基础理学类",     "本科及以上", "",       "A"),
        ("不限专业",                   "本科及以上", "",       "C"),
        ("教育学类（生物方向）",       "本科及以上", "",       "B"),
        ("生物技术、生物工程",         "本科及以上", "",       "D"),
        ("生物科学",                   "本科及以上", "须具有高级中学生物学科教师资格证", "B"),
        ("生物科学",                   "硕士研究生及以上", "", "D"),
    ]
    ok = True
    for text, edu, extra, expect in cases:
        job = {"专业要求原文": text, "学历要求": edu, "专业目录归属": tag_majors(text),
               "其他条件": extra, "备注": ""}
        level, reason, call = classify(job)
        flag = "[通过]" if level == expect else "[失败]"
        if level != expect:
            ok = False
        print("%s 专业=%-22s 学历=%-10s -> %s（期望 %s）| %s | 需咨询: %s"
              % (flag, text, edu, level, expect, reason, call))
    print("\n自检%s" % ("全部通过" if ok else "存在失败用例"))
    return 0 if ok else 1


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_argparser().parse_args(argv)
    setup_logging(args.verbose)

    if args.selftest:
        return selftest()

    started = datetime.now(CST)
    scraped_at = started.isoformat(timespec="seconds")
    # --check-only 与 --dry-run 都不允许写任何文件
    # （踩过的坑：--check-only 也会顺手更新 data.json 的 meta，导致本地与机器人提交冲突）
    no_write = bool(args.dry_run or args.check_only)
    fresh: List[Dict[str, object]] = []
    warnings: List[str] = []
    sources_meta: List[Dict[str, object]] = []
    local_mode = bool(args.local)

    # ------------------------------------------------------------------ #
    # 模式 A：解析本地已下载的官方职位表（最稳定，推荐）
    # ------------------------------------------------------------------ #
    if local_mode:
        # 先分流：文件名含「电话」的当咨询电话表，其余当职位表
        job_files: List[str] = []
        phone_files: List[str] = list(args.phone_file or [])
        for path in args.local:
            if not os.path.exists(path):
                warnings.append("本地文件不存在：%s" % path)
                log.error("本地文件不存在：%s", path)
                continue
            base = os.path.basename(path)
            if "电话" in base or "phone" in base.lower():
                if path.lower().endswith((".zip", ".rar", ".7z")):
                    phone_files.extend(extract_docs_from_archive(path))
                else:
                    phone_files.append(path)
            else:
                job_files.append(path)

        # 咨询电话索引（(城市,单位) -> 电话）
        regions = load_region_map()
        phone_entries: List[Tuple[str, str, str]] = []
        for pf in phone_files:
            rows_ = parse_phone_table(pf)
            if rows_:
                log.info("  电话表 %s -> %d 条", os.path.basename(pf), len(rows_))
            phone_entries.extend(rows_)
        phone_index = build_phone_index(phone_entries, regions) if phone_entries else {}
        if phone_entries:
            log.info("  咨询电话索引：%d 条电话记录 -> %d 个键", len(phone_entries), len(phone_index))
        elif phone_files:
            warnings.append("提供了电话表但没解析出内容（.doc 旧格式请先另存为 .docx）")

        for path in job_files:
            try:
                df = read_excel_all_sheets(path)
            except Exception as exc:
                warnings.append("解析失败 %s：%s" % (os.path.basename(path), exc))
                log.error("解析失败：%s（%s）", path, exc)
                continue
            # 年度：优先 --year，其次从文件名识别；都识别不到时给出明确提示（避免默默写成错误年度）
            file_year = args.year or guess_year(os.path.basename(path))
            if not file_year:
                fallback_year = derive_exam_year(args.exam_type, None, "")
                log.warning("  未能从文件名识别年度，将按 %d 年处理；如需修正请加 --year 参数（例如 --year %d）",
                            fallback_year, started.year)
            jobs = rows_to_jobs(df, exam_type=args.exam_type, year=file_year,
                                source_url=args.source_url or "（本地文件，无在线链接）",
                                source_name=args.source_name or "本地导入的官方职位表",
                                source_file=os.path.basename(path), scraped_at=scraped_at,
                                phone_index=phone_index, regions=regions)
            log.info("  %s -> 解析出 %d 条职位", os.path.basename(path), len(jobs))
            fresh.extend(jobs)
            sources_meta.append({
                "source_name": args.source_name or "本地导入",
                "exam_type": args.exam_type,
                "file": os.path.basename(path),
                "url": args.source_url,
                "records": len(jobs),
                "fetched_at": scraped_at,
            })

        if phone_entries and fresh:
            filled = sum(1 for j in fresh if clean_text(j.get("咨询电话")))
            note = ("咨询电话已从官方《招录单位咨询电话》回填 %d/%d 条（%.0f%%；"
                    "其余为未在电话表中列明的单位，如「乡镇机关」「区教育局」）" % (
                        filled, len(fresh), 100.0 * filled / len(fresh)))
            log.info("  " + note)
            warnings.append(note)

    # ------------------------------------------------------------------ #
    # 模式 B：联网抓取官方渠道
    # ------------------------------------------------------------------ #
    else:
        all_hosts = sorted({h for s in SOURCES for h in s.allowed_hosts})
        sess = PoliteSession(delay=args.delay, allowed_hosts=all_hosts)
        sess.strict_tls = args.strict_tls
        if not HAS_REQUESTS:
            log.warning("未安装 requests，已退回标准库 urllib（建议 pip install requests）")

        # 总时间预算：境外网络访问国内政府站点常是"连接挂起"，必须有个总闸
        deadline = (time.time() + args.time_budget) if args.time_budget and args.time_budget > 0 else None
        if deadline:
            log.info("本次抓取总时间预算：%d 秒（到点就停，避免撞上任务超时）", args.time_budget)

        skipped_sources: List[str] = []
        collected: List[Attachment] = []          # 所有数据源发现的附件，最后统一分两批处理
        for src in SOURCES:
            if deadline and time.time() > deadline:
                skipped_sources.append(src.name)
                continue
            log.info("═══ 数据源：%s ═══", src.name)
            try:
                stat = discover_attachments(sess, src, max_pages=args.max_pages, deadline=deadline)
            except Exception as exc:
                warnings.append("%s 抓取异常：%s" % (src.name, exc))
                log.warning("  抓取异常：%s", exc)
                continue

            log.info("  访问 %d 个页面，发现 %d 个候选附件%s", stat.pages_visited, len(stat.attachments),
                     ("（另有 %d 个非公务员附件已过滤，如事业单位岗位表）" % stat.filtered) if stat.filtered else "")
            if stat.errors:
                warnings.append("%s 有 %d 个页面打开失败" % (src.name, len(stat.errors)))
            for err in stat.errors[:3]:
                log.info("    · %s", err)

            if args.check_only:
                for a in stat.attachments:
                    print("  [发现] %s -> %s" % (a.title[:50], a.url))
                sources_meta.append({"source_name": src.name, "pages": stat.pages_visited,
                                     "attachments": len(stat.attachments)})
                continue
            collected.extend(stat.attachments)

        # 国考：专题站是 JS 应用，走官方数据接口（年度专题 id 由官方脚本给出，自动跟随）
        try:
            gk_atts, gk_meta = discover_guokao_api(sess)
            if gk_atts:
                log.info("  国考官方接口：%s → 发现 %d 个职位表附件",
                         gk_meta.get("topic") or "（未知专题）", len(gk_atts))
                for a in gk_atts:
                    log.info("    · %s", a.title[:60])
                    if args.check_only:
                        print("  [发现] %s -> %s" % (a.title[:50], a.url))
                if not args.check_only:
                    collected.extend(gk_atts)
            else:
                log.info("  国考官方接口：%s → 暂无可下载职位表",
                         gk_meta.get("topic") or "（未取到专题信息）")
        except Exception as exc:
            warnings.append("国考官方接口异常：%s" % exc)
            log.warning("  国考官方接口异常：%s", exc)

        # 两批处理：先电话表（建立索引），再职位表（用索引回填咨询电话）
        # 顺序很重要——否则职位表先解析时还没有电话可填。
        regions = load_region_map()
        phone_entries: List[Tuple[str, str, str]] = []
        for att in [a for a in collected if a.kind == "phone"]:
            try:
                got = download_and_parse_phone(sess, att)
            except Exception as exc:
                warnings.append("电话表下载/解析失败 %s：%s" % (att.url, exc))
                continue
            if got:
                log.info("  [电话] %s -> %d 条", att.title[:40], len(got))
            phone_entries.extend(got)
        phone_index = build_phone_index(phone_entries, regions) if phone_entries else {}
        if phone_entries:
            log.info("  咨询电话索引：%d 条电话记录 -> %d 个键", len(phone_entries), len(phone_index))

        if not args.check_only:
            for att in [a for a in collected if a.kind != "phone"]:
                try:
                    files = download_attachment(sess, att, DOWNLOAD_DIR)
                except Exception as exc:
                    warnings.append("下载失败 %s：%s" % (att.url, exc))
                    continue
                for file_path in files:
                    try:
                        df = read_excel_all_sheets(file_path)
                        jobs = rows_to_jobs(
                            df, exam_type=att.exam_type, year=att.year,
                            source_url=att.page_url, source_name=att.source_name,
                            source_file=os.path.basename(file_path), scraped_at=scraped_at,
                            phone_index=phone_index, regions=regions)
                    except Exception as exc:
                        warnings.append("解析失败 %s：%s" % (os.path.basename(file_path), exc))
                        log.warning("  解析失败 %s：%s", file_path, exc)
                        continue
                    log.info("  [OK] %s -> %d 条职位", os.path.basename(file_path), len(jobs))
                    fresh.extend(jobs)
                    sources_meta.append({
                        "source_name": att.source_name,
                        "exam_type": att.exam_type,
                        "title": att.title,
                        "file": os.path.basename(file_path),
                        "url": att.page_url,
                        "attachment_url": att.url,
                        "records": len(jobs),
                        "fetched_at": scraped_at,
                    })

        if skipped_sources:
            warnings.append("时间预算 %d 秒用尽，本次跳过 %d 个数据源（%s）"
                            % (args.time_budget, len(skipped_sources),
                               "、".join(skipped_sources[:3]) + ("…" if len(skipped_sources) > 3 else "")))
            log.warning("时间预算用尽，跳过剩余 %d 个数据源", len(skipped_sources))

        if sess.skipped:
            warnings.append("遵守 robots.txt 跳过 %d 个链接" % len(sess.skipped))

    # ------------------------------------------------------------------ #
    # 收窄范围 + 合并 + 输出
    # ------------------------------------------------------------------ #
    if args.scope == "jiangsu-biology":
        before = len(fresh)
        fresh = [j for j in fresh if is_jiangsu(j) and is_relevant_biology(j)]
        log.info("范围收窄（江苏 + 生物相关）：%d -> %d 条", before, len(fresh))

    # 定向招录岗位（面向服务基层项目人员/优秀村书记/残疾人/法官检察官助理）默认排除：
    # 这类岗位本科应届一般报不了，留着会把"不限专业"结果淹没
    if not args.include_targeted:
        before = len(fresh)
        fresh = [j for j in fresh if not is_targeted(j)]
        excluded = before - len(fresh)
        if excluded:
            log.info("已排除 %d 个定向招录岗位（如面向服务基层项目人员/优秀村书记/残疾人）；"
                     "如需保留请加 --include-targeted", excluded)
            warnings.append("已排除 %d 个定向招录岗位（本科应届一般不符合报考对象），如需查看请加 --include-targeted" % excluded)

    # 同一批次内去重
    dedup: Dict[str, Dict[str, object]] = {}
    for j in fresh:
        dedup[job_key(j)] = j
    fresh = list(dedup.values())

    existing, old_meta = ({}, {}) if args.no_merge else load_existing(args.output)
    merged, added, updated = merge_jobs(existing, fresh)

    # 年度策略：默认只保留每类考试的最新年度 —— 官方发布新年度职位表后，
    # 旧年度记录会被自动替换掉（这就是"有新表就替换旧表"）
    merged, cycle_years, dropped_years = apply_year_policy(merged, args.year_policy)
    if dropped_years:
        log.info("年度策略（%s）：仅保留最新年度 %s，已丢弃旧年度 %s 的记录；"
                 "如需保留历年请加 --year-policy keep-all",
                 args.year_policy,
                 "、".join("%s %d" % (k, v) for k, v in cycle_years.items()),
                 "、".join(str(y) for y in dropped_years))
        warnings.append("已按年度策略仅保留最新年度记录（丢弃 %s）；如需保留历年请加 --year-policy keep-all"
                        % "、".join(str(y) for y in dropped_years))

    merged.sort(key=lambda j: (clean_text(j.get("考试类型")), clean_text(j.get("年度")),
                               clean_text(j.get("招录机关"))), reverse=True)

    # 关键安全阀：本次没有抓到任何新数据时，绝不覆盖既有 data.json
    if not fresh:
        log.error("[跳过] 本次未获取到任何官方职位数据，已保留原有 data.json 不变。")
        print("\n" + "=" * 72)
        print("未获取到新数据，可能原因与建议：")
        print("  1) 官方专题页尚未发布/尚未到发布期（国考通常 10 月、江苏省考通常 10-11 月）；")
        print("  2) 目标网站对境外 IP（如 GitHub Actions 运行环境）限制访问；")
        print("  3) 页面为 JS 动态渲染，或附件为 .rar 需人工解压。")
        print("  建议：在本地浏览器下载官方职位表 Excel 后，执行：")
        print("      python scraper.py --local 你的职位表.xlsx --exam-type 江苏省考 --year %d \\" % (started.year + 1))
        print("          --source-url https://官方公告页面地址")
        print("=" * 72 + "\n")
        if not existing:
            warnings.append("首次运行未获取到数据，未生成 data.json（不编造数据）")
            if not no_write:
                log.error("不写入任何文件（绝不编造职位数据）。")
            return 2
        # 有历史数据：只更新 meta 中的告警信息，不动 jobs
        old_meta = dict(old_meta or {})
        old_meta["warnings"] = (old_meta.get("warnings") or [])[:0] + warnings + \
            ["本次(%s)定时抓取未发现新职位表，数据保持为上一次抓取结果" % started.strftime("%Y-%m-%d %H:%M")]
        old_meta["last_check"] = scraped_at
        if not no_write:
            write_data_json(args.output, merged, old_meta)
        return 2

    data_status = ("local-import" if local_mode else "official") if args.data_status == "auto" else args.data_status
    if data_status == "sample":
        # 明确标注为示例数据，避免与真实职位混淆（前端会显示红色"示例数据"角标）
        for j in merged:
            j["是否示例"] = True
        warnings.append("当前 data.json 为格式示例数据，不是真实职位，请以官方职位表为准")

    # sources：与旧 meta 合并，避免"只导入国考/只导入省考"时把另一边的来源记录抹掉
    # （每条职位自身也带 来源链接/来源文件，这里只是 meta 层的汇总）
    merged_sources: List[Dict[str, object]] = []
    seen_src: set = set()
    for s in list(sources_meta) + list((old_meta or {}).get("sources") or []):
        key = (clean_text(s.get("source_name")), clean_text(s.get("file") or s.get("title")))
        if key in seen_src:
            continue
        seen_src.add(key)
        merged_sources.append(s)

    meta = {
        "last_update": scraped_at,
        "last_update_text": started.strftime("%Y-%m-%d %H:%M") + "（北京时间）",
        "last_check": scraped_at,
        "generator": "scraper.py",
        "data_status": data_status,
        "record_count": len(merged),
        "new_records": added,
        "updated_records": updated,
        "scope": args.scope,
        "exam_types": sorted({clean_text(j.get("考试类型")) for j in merged if j.get("考试类型")}),
        "sources": merged_sources,
        "warnings": warnings,
        "disclaimer": "数据来自官方公开职位表，仅供筛选参考；报考条件以官方公告、职位表原件及招录单位答复为准。",
    }

    if no_write:
        log.info("%s：解析到 %d 条（合并后 %d 条），未写入文件",
                 "--check-only" if args.check_only else "--dry-run", len(fresh), len(merged))
    else:
        write_data_json(args.output, merged, meta)
        log.info("已写入 %s：共 %d 条（新增 %d，更新 %d）", args.output, len(merged), added, updated)

    # 打印摘要，便于在 Actions 日志中快速查看
    print("\n" + "=" * 72)
    print("抓取完成：%s" % started.strftime("%Y-%m-%d %H:%M:%S %Z"))
    print("输出文件：%s" % args.output)
    print("职位总数：%d（新增 %d / 更新 %d）" % (len(merged), added, updated))
    levels: Dict[str, int] = {}
    for j in merged:
        levels[clean_text(j.get("匹配结论"))] = levels.get(clean_text(j.get("匹配结论")), 0) + 1
    print("匹配结论分布：" + " ".join("%s=%d" % (k, v) for k, v in sorted(levels.items())))
    if warnings:
        print("告警：")
        for w in warnings:
            print("  ! " + w)
    print("=" * 72 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
