import logging
import os
import re
import urllib.parse
from typing import Iterator

import requests
from lxml.etree import HTML, Element
from rich import print
from rich.logging import RichHandler
from rich.progress import track
from rich.prompt import Prompt
from rich.traceback import install

install()

FORMAT = '%(message)s'
logging.basicConfig(
    level='INFO',
    format=FORMAT,
    datefmt='[%X]',
    handlers=[RichHandler(rich_tracebacks=True)]
)

log = logging.getLogger('rich')


class Yinfu:
    def __init__(self):
        self.session = requests.session()

    def getFileName(self, Response: requests.Response) -> str:
        disposition = Response.headers.get('Content-Disposition')
        filename = disposition.split('filename=')[1]
        filename = filename.replace('"', '')
        filename = urllib.parse.unquote(filename)
        return filename

    def download(self, suID, exID, where='downloads') -> None | str:
        self.session.get(
            'https://www.yfzxmn.cn/examTab_getExam.action',
            params={'su_Id': suID, 'ex_Id': exID},
        )

        downWord = self.session.get(
            'https://www.yfzxmn.cn/download.action',
            params={'su_Id': suID, 'ex_Id': exID},
        ).text

        realLink = re.findall(r'href="(.*?)"', downWord)[0]

        resp = self.session.get(realLink, stream=True)
        fileName = self.getFileName(resp)

        if not os.path.exists(where):
            os.makedirs(where)
        if os.path.exists(f'{where}/{fileName}'):
            print(f'文件 [red][not bold]{where}/{fileName}[/not bold][/red] 已存在')
            return 'Error'

        with open(f'{where}/{fileName}', 'wb') as f:
            for i in resp.iter_content():
                f.write(i)

    def getHotExam(self, suID) -> Iterator[tuple[str, str]]:
        '''获取热门考试'''
        hotExam = self.session.post(
            'https://www.yfzxmn.cn/examTab_getHotExam.action',
            data={'su_Id': suID}
        ).json()

        for i in track(hotExam['ExaminationTab']):
            yield i['ex_Id'], i['ex_Name']

    def downloadHotExam(self, suID) -> None:
        '''下载热门考试'''
        for i, j in self.getHotExam(suID):
            print(f"Downloading {j}")
            self.download(suID, i)

    def getCategories(self) -> Iterator[Element]:
        '''返回有 suid 属性的 Element'''
        yfzxmn = self.session.get('https://www.yfzxmn.cn/').text
        yfzxmn = HTML(yfzxmn)

        titles = yfzxmn.xpath('//div[@suid]')
        for i in titles:
            yield i

    def getSubjects(self, suID) -> Iterator[Element]:
        '''获取科目'''
        examTab = self.session.get(
            'https://www.yfzxmn.cn/examTab_get.action',
            params={'su_Id': suID}
        ).text
        examTab = HTML(examTab)

        titles = examTab.xpath('//div[@class="left"]//a[@title]')
        for i in titles:
            # 返回的是 a 元素，需要获取 title 和 href 属性
            yield i

    def getCount(self, suID, soID) -> tuple[int, int]:
        '''获取页数'''
        examTab = self.session.get(
            'https://www.yfzxmn.cn/examTab_get.action',
            params={'su_Id': suID, 'so_Id': soID}
        ).text
        examTab = HTML(examTab)

        script = examTab.xpath('//div[@id="paging2"]//script/text()')[0]
        totalPages = re.findall(r'(\d+),', script)[0]

        text = examTab.xpath('//div[@class="center"]//font/text()')[0]
        totalExams = re.findall(r'(\d+)', text)[0]

        return int(totalPages), int(totalExams)

    def getExamTab(self, suID, soID, nowPage) -> Iterator[Element]:
        '''获取考试列表'''
        examTab = self.session.get(
            'https://www.yfzxmn.cn/examTab_get.action',
            params={'su_Id': suID, 'so_Id': soID, 'nowPage': nowPage}
        ).text
        examTab = HTML(examTab)

        trs = examTab.xpath('//div[@class="exam"]//tr[not(@class)]')
        for i in trs:
            # 返回的是 tr 元素，需要获取 td 元素
            yield i

    def getExams(self, suId: int | str, soId: int | str, nowPage: int | str) -> Iterator[tuple[str, str, str, str]]:
        '''从考试列表获取考试信息'''
        for i in self.getExamTab(suId, soId, nowPage):
            name = i.xpath('.//td[1]/text()')[0].strip()
            hasAns = i.xpath('.//td[2]/text()')[0].strip()
            updateTime = i.xpath('.//td[3]/text()')[0].strip()
            href = i.xpath('.//a/@href')[0]
            yield name, hasAns, updateTime, href

    def chooseCategory(self) -> int | str:
        categories = []
        for i, j in enumerate(self.getCategories()):
            suName = j.xpath('.//a[@class="suName"]')[0]
            href = suName.get('href')

            suID = re.findall(r'su_Id=(\d+)', href)[0]
            categories.append(suID)

            print(
                f'{i+1}: [green][not bold]{suName.text}[/not bold][/green]')

        which = Prompt.ask(
            '请选择分类（回车退出）',
            show_default=False,
            default='exit'
        )
        if which == 'exit':
            return None
        elif which.isnumeric():
            which = int(which)
            suID = categories[which-1]
        else:
            print('[red]请输入正确的序号[/red]')
            return 'Error'

        while True:
            subject = self.chooseSubject(suID)
            if subject is None:
                break

        return suID

    def chooseSubject(self, suID) -> int | str:
        subjects = []
        for i, j in enumerate(self.getSubjects(suID)):
            title = j.get('title')
            href = j.get('href')

            soID = re.findall(r'so_Id=(\d+)', href)[0]
            subjects.append(soID)

            print(f'{i+1}: [green][not bold]{title}[/not bold][/green]')

        which = Prompt.ask(
            '请选择科目（回车返回）',
            show_default=False,
            default='exit'
        )
        if which == 'exit':
            return None
        elif which.isnumeric():
            which = int(which)
            soID = subjects[which-1]
        else:
            print('[red]请输入正确的序号[/red]')
            return 'Error'

        while True:
            exams = self.chooseExams(suID, soID)
            if exams is None:
                break

        return soID

    def chooseExams(self, suID, soID) -> int | str:
        exams = []
        selectedExams = set()
        nowPage = 1

        totalPages, totalExams = self.getCount(suID, soID)
        loadedPages = set()

        while True:
            if nowPage not in loadedPages:
                for name, hasAns, updateTime, href in self.getExams(suID, soID, nowPage):
                    count, name = name.split('、')

                    exID = re.findall(r'ex_Id=(\d+)', href)[0]
                    exams.append({'name': name,
                                  'hasAns': hasAns,
                                  'updateTime': updateTime,
                                  'exID': exID,
                                  'selected': False})

                    print(
                        f'{int(count)}: [green][not bold]{name}[/not bold][/green]'
                    )
                loadedPages.add(nowPage)
            else:
                examFrom = (nowPage-1)*20
                examTo = min(nowPage*20, len(exams))
                for i in range(examFrom, examTo):
                    selected = exams[i]['selected']
                    print(
                        f'{"=> " if selected else ""}{i+1}: [green][not bold]{exams[i]["name"]}[/not bold][/green]'
                    )

            print(
                f'第 {nowPage}/{totalPages} 页，共有 {totalExams} 张试卷，已选择 {len(selectedExams)} 张'
            )

            print(
                '[yellow]ok[/yellow]: 下载|'
                '[yellow]n[/yellow]: 下一页|'
                '[yellow]p[/yellow]: 上一页|'
                '[yellow]r[/yellow]: 反选'
            )
            which = Prompt.ask(
                '请选择试卷（回车返回）',
                show_default=False,
                default='exit'
            )
            match which.split():
                case ['e'] | ['exit']:
                    return None
                case ['o'] | ['ok']:
                    break
                case ['n'] | ['next']:
                    nowPage += 1
                    if nowPage > totalPages:
                        nowPage = 1
                    continue
                case ['n', n] | ['next', n]:
                    nowPage += int(n)
                    if nowPage > totalPages:
                        # TODO 加入循环翻页
                        nowPage = totalPages
                    continue
                case ['p'] | ['prev']:
                    nowPage -= 1
                    if nowPage < 1:
                        nowPage = 1
                    continue
                case ['p', n] | ['prev', n]:
                    nowPage -= int(n)
                    if nowPage < 1:
                        # TODO 加入循环翻页
                        nowPage = 1
                    continue
                case ['r'] | ['reverse']:
                    examFrom = (nowPage-1)*20
                    examTo = min(nowPage*20, len(exams))
                    these = range(examFrom+1, examTo+1)
                case _:
                    if '-' in which:
                        f, t = which.split('-')
                        these = range(int(f), int(t)+1)
                    elif ',' in which:
                        these = [int(i) for i in which.split(',')]
                    elif which.isnumeric():
                        these = [int(which)]
                    else:
                        print('[red]请输入正确的序号[/red]')
                        continue

            # 选择试卷
            deletedExams = set()
            for i in these:
                exams[i-1]['selected'] = not exams[i-1]['selected']
                if i-1 in selectedExams:
                    deletedExams.add(i-1)
                else:
                    selectedExams.add(i-1)
            selectedExams -= deletedExams

        # 下载试卷
        selectedExams = list(selectedExams)
        selectedExams.sort()
        for i in track(selectedExams, '下载中'):
            print(
                f'正在下载: [blue][not bold]{exams[i]["name"]}[/not bold][/blue]'
            )
            error = self.download(suID, exams[i]['exID'])
            if error is None:
                print(
                    f'下载 [green][not bold]{exams[i]["name"]}[/not bold][/green] 成功'
                )
        print(f'下载 {len(selectedExams)} 张试卷成功')
        return True

    def main(self) -> None:
        while True:
            suID = self.chooseCategory()
            if suID is None:
                break


if __name__ == '__main__':
    yf = Yinfu()
    yf.main()
