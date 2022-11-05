from python_graphql_client import GraphqlClient
import feedparser
import httpx
import json
import pathlib
import re
import os
import datetime
from prettytable import PrettyTable
import aiohttp
import asyncio
root = pathlib.Path(__file__).parent.resolve()
client = GraphqlClient(endpoint="https://api.github.com/graphql")


TOKEN = os.environ.get("YJT_TOKEN", "")


def replace_chunk(content, marker, chunk, inline=False):
    r = re.compile(
        r"<!\-\- {} starts \-\->.*<!\-\- {} ends \-\->".format(marker, marker),
        re.DOTALL,
    )
    if not inline:
        chunk = "\n{}\n".format(chunk)
    chunk = "<!-- {} starts -->{}<!-- {} ends -->".format(marker, chunk, marker)
    return r.sub(chunk, content)


organization_graphql = """
  organization(login: "dogsheep") {
    repositories(first: 100, privacy: PUBLIC) {
      pageInfo {
        hasNextPage
        endCursor
      }
      nodes {
        name
        description
        url
        releases(orderBy: {field: CREATED_AT, direction: DESC}, first: 1) {
          totalCount
          nodes {
            name
            publishedAt
            url
          }
        }
      }
    }
  }
"""


def make_query(after_cursor=None, include_organization=False):
    return """
query {
  ORGANIZATION
  viewer {
    repositories(first: 100, privacy: PUBLIC, after: AFTER) {
      pageInfo {
        hasNextPage
        endCursor
      }
      nodes {
        name
        description
        url
        releases(orderBy: {field: CREATED_AT, direction: DESC}, first: 1) {
          totalCount
          nodes {
            name
            publishedAt
            url
          }
        }
      }
    }
  }
}
""".replace(
        "AFTER", '"{}"'.format(after_cursor) if after_cursor else "null"
    ).replace(
        "ORGANIZATION", organization_graphql if include_organization else "",
    )

def formatGMTime(timestamp):
    GMT_FORMAT = '%a, %d %b %Y %H:%M:%S GMT'
    dateStr = datetime.datetime.strptime(timestamp, GMT_FORMAT) + datetime.timedelta(hours=8)
    return dateStr.date()
def fetch_releases(oauth_token):
    repos = []
    releases = []
    repo_names = set()
    has_next_page = True
    after_cursor = None

    while has_next_page:
        data = client.execute(
            query=repository_query(after_cursor),
            headers={"Authorization": "Bearer {}".format(oauth_token)},
        )
        for repo in data["data"]["viewer"]["repositories"]["nodes"]:
            if repo["releases"]["totalCount"] and repo["name"] not in repo_names:
                repos.append(repo)
                repo_names.add(repo["name"])
                releases.append(
                    {
                        "repo": repo["name"],
                        "repo_url": repo["url"],
                        "description": repo["description"],
                        "release": repo["releases"]["nodes"][0]["name"]
                            .replace(repo["name"], "")
                            .strip(),
                        "published_at": repo["releases"]["nodes"][0][
                            "publishedAt"
                        ].split("T")[0],
                        "url": repo["releases"]["nodes"][0]["url"],
                    }
                )
        has_next_page = data["data"]["viewer"]["repositories"]["pageInfo"][
            "hasNextPage"
        ]
        after_cursor = data["data"]["viewer"]["repositories"]["pageInfo"]["endCursor"]
    return releases


def fetch_tils():
    sql = """
        select path, replace(title, '_', '\_') as title, url, topic, slug, created_utc
        from til order by created_utc desc limit 5
    """.strip()
    return httpx.get(
        "https://til.simonwillison.net/tils.json",
        params={"sql": sql, "_shape": "array",},
    ).json()


def fetch_blog_entries():
    entries = feedparser.parse("https://wuyuler.github.io/feed.xml")["entries"]
    return [
        {
            "title": entry["title"],
            "url": entry["link"].split("#")[0],
            "published": entry["published"].split("T")[0],
        }
        for entry in entries
    ]

def fetch_douban():
    entries = feedparser.parse("https://www.douban.com/feed/people/247254851/interests")["entries"]
    return [
        {
            "title": item["title"],
            "url": item["link"].split("#")[0],
            "published": formatGMTime(item["published"])
        }
        for item in entries
    ]

class ExportMD:
    def __init__(self):
        self.repo_table = PrettyTable(["知识库ID", "名称"])
        # self.namespace, self.Token = self.get_UserInfo()
        self.namespace="yongyule"
        self.Token="ff2jIOU0aWA4onGzY0t22PaS2rdtLrar0ojY5f67"
        self.headers = {
            "Content-Type": "application/json",
            "User-Agent": "ExportMD",
            "X-Auth-Token": self.Token
        }
        self.repo = {}
        self.export_dir = './yuque'
        self.titles={}


    # 发送请求
    async def req(self, session, api):
        url = "https://www.yuque.com/api/v2" + api
        async with session.get(url, headers=self.headers) as resp:
            result = await resp.json()
            return result

    # 获取所有知识库
    async def getRepo(self):
        api = "/users/%s/repos" % self.namespace
        async with aiohttp.ClientSession() as session:
            result = await self.req(session, api)
            for repo in result.get('data'):
                repo_id = str(repo['id'])
                repo_name = repo['name']
                self.repo[repo_name] = repo_id
                self.repo_table.add_row([repo_id, repo_name])

    # 获取一个知识库的文档列表
    async def get_docs(self, repo_id):
        api = "/repos/%s/docs" % repo_id
        async with aiohttp.ClientSession() as session:
            result = await self.req(session, api)
            entries = result.get('data')
            return [{
                "title":entry["title"],
                "url":"https://www.yuque.com/yongyule/xkp8qg/"+entry["slug"],
                "published": entry["published_at"][:10]
            } for entry in entries]

    async def run(self):
        # self.print_logo()
        await self.getRepo()
        TIL_id=self.repo["TIL"]
        docs = await self.get_docs(TIL_id)
        sorted(docs, key=lambda x: x["published"])
        self.titles=docs[:5]
if __name__ == "__main__":
    readme = root / "README.md"
    readme_contents = readme.open().read()
    # 个人博客
    entries = fetch_blog_entries()[:5]
    entries_md = "\n\n".join(
        ["[{title}]({url}) - {published}".format(**entry) for entry in entries]
    )
    rewritten = replace_chunk(readme_contents, "blog", entries_md)
    # 豆瓣
    doubans = fetch_douban()[:5]
    doubans_md = "\n".join(
        ["* <a href='{url}' target='_blank'>{title}</a> - {published}".format(**item) for item in doubans]
    )
    rewritten = replace_chunk(rewritten, "douban", doubans_md)
    #TIL
    export = ExportMD()
    export.namespace="yongyule"
    export.Token="ff2jIOU0aWA4onGzY0t22PaS2rdtLrar0ojY5f67"
    export.getRepo()
    # print("test")
    loop = asyncio.get_event_loop()
    loop.run_until_complete(export.run())
    til_md== "\n".join(
        ["* <a href='{url}' target='_blank'>{title}</a> - {published}".format(**item) for item in export.titles]
    )
    rewritten = replace_chunk(rewritten, "til", til_md) 
    readme.open("w").write(rewritten)
