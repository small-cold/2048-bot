import sys
import time
import random
import traceback
from datetime import datetime
import logging

from selenium.webdriver.common.by import By
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from ai import *
from move import *

DEFAULT_GAME_URL = 'https://play2048.co/'

class Algorithm(Enum):
    ALPHABETA = 1,
    EXPECTIMAX = 2


class Game2048:

    def __init__(self, game_url: str = DEFAULT_GAME_URL):
        self.logger = logging.getLogger('2048_game')
        self.game_url = game_url
        self.engine2048 = Engine2048()
        try:
            chrome_options = Options()
            chrome_options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")  # 连接到已打开的Chrome
            chrome_options.add_argument("--disable-background-timer-throttling")  # 禁用后台计时器限制
            chrome_options.add_argument("--disable-backgrounding-occluded-windows")  # 禁用背景窗口限制
            chrome_options.add_argument("--disable-renderer-backgrounding")  # 禁用渲染器后台处理
            self.browser = webdriver.Chrome(options=chrome_options)
        except Exception as e:
            self.logger.error(f"无法连接到已打开的Chrome，将启动新的浏览器窗口", exc_info=True)
            chrome_options = Options()
            chrome_options.add_argument("--remote-debugging-port=9222")  # 开启调试端口
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])  # 防止浏览器自动关闭
            chrome_options.add_experimental_option('useAutomationExtension', False)  # 防止浏览器自动关闭
            self.browser = webdriver.Chrome(options=chrome_options)
            self.browser.get(url=self.game_url)
            # self.browser.set_window_position(0, 0)
            # self.browser.set_window_size(1024, 1024)
        self.htmlElem = self.browser.find_element(By.TAG_NAME, 'html')
        self.actual_score = 0
        self.has_won_flag = False
        self.tile_scores = []

    def __del__(self):
        # 析构函数，确保浏览器不会自动关闭
        pass

    def parse_web_content(self):
        """
        Parses the 2048 game in the Web-browser.
        """
        # Parse the current score
        try:
            elem = self.browser.find_element(By.CLASS_NAME, 'score-container')
            # 使用 JavaScript 获取第一个子节点的文本内容
            if elem.text == '':
                self.actual_score = int(self.browser.execute_script("return arguments[0].firstChild.textContent", elem))
            else:
                self.actual_score = int(elem.text)
        except Exception as e:
            self.logger.error(f"获取分数失败", exc_info=True)
            pass

        game = Grid2048()

        range_str = ["1", "2", "3", "4"]

        # Parse the grid
        for x in range_str:
            for y in range_str:
                try:
                    elements = self.browser.find_elements(By.CLASS_NAME, 'tile-position-' + x + '-' + y)
                    max_grid_cell_val = 0

                    if len(elements) > 0:
                        for elem in elements:
                            if elem != '':
                                if int(elem.text) > max_grid_cell_val:
                                    max_grid_cell_val = int(elem.text)

                        game.insert(int(y) - 1, int(x) - 1, max_grid_cell_val)

                except:
                    print('Not found')

        return game

    def move_web_grid(self, move: EMove):
        """
        Moves the game in the web browser.
        """
        if move == EMove.LEFT:
            self.htmlElem.send_keys(Keys.LEFT)

        if move == EMove.RIGHT:
            self.htmlElem.send_keys(Keys.RIGHT)

        if move == EMove.UP:
            self.htmlElem.send_keys(Keys.UP)

        if move == EMove.DOWN:
            self.htmlElem.send_keys(Keys.DOWN)

    def check_promo_code(self):
        """
        检查是否出现优惠码模态框，如果出现则保存信息
        返回是否应该继续执行（折扣是否为50%）
        """
        try:
            # 检查模态框是否存在
            modal = self.browser.find_element(By.ID, "modal-close-default")
            if modal.is_displayed():
                # 获取标题
                promo_title = self.browser.find_element(By.ID, "promo_code_h2").text.strip()
                
                # 检查是否是没有获得优惠码的情况
                if "Oh no! This time it did not work out" in promo_title:
                    time.sleep(3)
                    close_modal = self.browser.find_element(By.CLASS_NAME, "uk-modal-close-default")
                    close_modal.click()
                    self.logger.info("本次未获得优惠码，关闭模态框重新开始")
                    # self.htmlElem.send_keys(Keys.ESCAPE)  # 发送 ESC 键关闭模态框
                    time.sleep(1)  # 等待模态框关闭
                    return True  # 继续执行
                
                # 使用 JavaScript 获取优惠码文本（去除 strong 标签）
                promo_code = self.browser.execute_script(
                    "return arguments[0].querySelector('strong').textContent",
                    self.browser.find_element(By.ID, "promo_code_text")
                ).strip()
                
                # 使用 JavaScript 获取 IP 地址
                promo_ip = self.browser.execute_script(
                    "return arguments[0].querySelector('#promo_code_ip').textContent",
                    self.browser.find_element(By.ID, "promo_code_text2")
                ).strip()
                
                # 提取折扣比例（使用更安全的方式）
                try:
                    # 使用 JavaScript 直接获取折扣数字
                    discount = int(self.browser.execute_script(
                        "return arguments[0].querySelector('i').textContent",
                        self.browser.find_element(By.ID, "promo_code_h2")
                    ).strip().replace('%', ''))
                except Exception as e:
                    print(f"提取折扣比例失败: {e}")
                    print("标题内容:", promo_title)
                    # 如果提取失败，尝试从标题文本中提取
                    import re
                    match = re.search(r'(\d+)%', promo_title)
                    if match:
                        discount = int(match.group(1))
                    else:
                        print("无法从标题中提取折扣比例")
                        raise e
                
                # 保存到文件
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"coupon_codes.log"
                with open(filename, "a", encoding="utf-8") as f:
                    f.write("\n" + "="*50 + "\n")  # 添加分隔线
                    f.write(f"时间: {timestamp}\n")
                    f.write(f"优惠码: {promo_code}\n")
                    f.write(f"IP: {promo_ip}\n")
                    f.write(f"折扣: {discount}%\n")
                    f.write(f"标题: {promo_title}\n")
                    f.write("="*50 + "\n")  # 添加分隔线
                
                self.logger.info(f"已追加优惠码信息到 {filename}")
                self.logger.info(f"优惠码: {promo_code}")
                self.logger.info(f"折扣: {discount}%")
                # 如果折扣是50%，返回False表示应该结束执行
                if discount == 50:
                    return False
                close_modal = self.browser.find_element(By.CLASS_NAME, "uk-modal-close-default")
                close_modal.click()
                # self.htmlElem.send_keys(Keys.ESCAPE)  # 发送 ESC 键关闭模态框
                return True
        except Exception as e:
            self.logger.error(f"检查优惠码失败", exc_info=True)
            raise e
        
        return True  # 默认继续执行
    
    def restart_game(self):
        """
        重开页面，带重试机制
        """
        self.has_won_flag = False
        max_retries = 3
        for retry in range(max_retries):
            try:
                self.browser.find_element(By.CSS_SELECTOR, '.restart-button').click()
                time.sleep(2)
                return
            except Exception as e:
                self.logger.error(f"点击重新开始失败，第{retry + 1}次重试", exc_info=True)
                time.sleep(2)
                if not self.check_promo_code():
                    print("检查优惠码弹窗")
        
        self.logger.error(f"重启游戏失败{max_retries}次，尝试重新加载页面")
        try:
            self.browser.close()
            self.browser.get(url=self.game_url)
            time.sleep(3)
            self.htmlElem = self.browser.find_element(By.TAG_NAME, 'html')
        except Exception as e:
            self.logger.error("重新加载页面失败", exc_info=True)

    def run(self, nbr_runs: int, algorithm: Algorithm, heuristic: HeuristicScore, continue_high_score: bool = False):
        """
        Gets the parsed game and then runs the AI to get best move that will be used to move the
        game in the next direction.
        """
        scores = []
        wins = 0

        for i in range(nbr_runs):
            score = self._do_run(algorithm, heuristic, continue_high_score)
            scores.append(score)
            if self.has_won_flag:
                wins += 1
            else:
                self.logger.info(f"第{i}次游戏未获胜")
            self.logger.info(f"第{i}次游戏得分 {score} 获胜次数 {wins} 获胜概率 {round(wins / (i + 1), 2)} 平均得分 {round(sum(scores) / (i + 1))}")
            # ////////////////////////// NEW GAME //////////////////////////////
            if i < nbr_runs:
                self.restart_game()
        
        # 统计输出部分
        self.logger.info("///////////////// STATS ////////////////////////")
        self.logger.info(f"Number of wins {wins}")
        self.logger.info(f"Win probability {round(wins / nbr_runs, 2)}")
        self.logger.info(f"smallest score {min(scores)}")
        self.logger.info(f"Highest score {max(scores)}")
        self.logger.info(f"Average score {round(sum(scores) / nbr_runs)}")
        self.logger.info("Scores", scores)

        nbr_1024, nbr_2048, nbr_4096, nbr_8192 = 0, 0, 0, 0

        for i in range(nbr_runs):
            if 1024 in self.tile_scores[i]:
                nbr_1024 += self.tile_scores[i][1024]
            if 2048 in self.tile_scores[i]:
                nbr_2048 += self.tile_scores[i][2048]
            if 4096 in self.tile_scores[i]:
                nbr_4096 += self.tile_scores[i][4096]
            if 8192 in self.tile_scores[i]:
                nbr_8192 += self.tile_scores[i][8192]

        self.logger.info("1024 reached : ", nbr_1024)
        self.logger.info("2048 reached : ", nbr_2048)
        self.logger.info("4096 reached : ", nbr_4096)
        self.logger.info("8192 reached : ", nbr_8192)


    def _do_run(self, algorithm: Algorithm, heuristic: HeuristicScore, continue_high_score: bool = False):
        """
        Gets the parsed game and then runs the AI to get best move that will be used to move the
        game in the next direction.
        """

        tiles = {}
        while True:
            self.keep_system_active()
            game = self.parse_web_content()
            self.engine2048.bestMove = None
            if not self.has_won_flag:
                if game.has_won():
                    self.has_won_flag = True
                    # 检查优惠码
                    if not self.check_promo_code():
                        print("获得50%折扣，程序结束")
                        return
                    if not continue_high_score:
                        print("赢了，重新开始")
                        break
                    print("赢了，继续挑战")
                    time.sleep(5)
                    try:
                        self.browser.find_element(By.CSS_SELECTOR, '.keep-playing-button').click()
                        time.sleep(5)
                    except Exception as e:
                        print("点击失败，重试", e)
                        time.sleep(1)
            time.sleep(0.1)

            self.logger.info(f"-- gaming Score {self.actual_score} MaxTile {game.get_max_tile()}")

            # Find best move according to chosen algorithm.
            best_move = None

            if algorithm is Algorithm.ALPHABETA:
                best_move = self.engine2048.best_move_alphabeta(game, heuristic)

            elif algorithm is Algorithm.EXPECTIMAX:
                best_move = self.engine2048.best_move_expectimax(game, heuristic)

            self.move_web_grid(best_move)
            tiles = game.parse_tiles(tiles, 8)

            # 等待0.1秒~3秒
            time.sleep(random.uniform(0.1, 1))

            if best_move is None:
                print("没有可移动的方块，结束")
                break
        # ////////////////////////// STATS /////////////////////////////////
        score = self.actual_score
        self.actual_score = 0
        self.tile_scores.append(tiles)
        return score

    def keep_system_active(self):
        """
        定期执行一些操作来保持系统活跃
        """
        try:
            if time.time() - self.last_active_time > 300:
                self.last_active_time = time.time()
                self.browser.execute_script("window.focus();")  # 保持浏览器窗口焦点
        except:
            pass


""" MAIN PROGRAM --------------------------------- """


def setup_logger():
    """
    配置日志系统
    """
    # 创建一个logger对象
    logger = logging.getLogger('2048_game')
    logger.setLevel(logging.INFO)
    
    # 创建一个文件处理器，文件名包含时间戳
    timestamp = datetime.now().strftime("%Y%m%d%H")
    file_handler = logging.FileHandler(f'game_log_{timestamp}.log', encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    
    # 创建一个控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # 创建一个格式器，添加exc_info参数
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # 将处理器添加到logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger


def main(game_url: str = DEFAULT_GAME_URL):
    """
    主函数
    """
    logger = setup_logger()
    finished = False
    while not finished:
        try:
            game = Game2048(game_url)
            runs = 50
            # game.run(nbr_runs=runs, algorithm=Algorithm.ALPHABETA, heuristic=HeuristicScore.CORNER)
            # game.run(nbr_runs=runs, algorithm=Algorithm.ALPHABETA, heuristic=HeuristicScore.CORNERS)
            # game.run(nbr_runs=runs, algorithm=Algorithm.ALPHABETA, heuristic=HeuristicScore.SNAKE)
            game.run(nbr_runs=runs, algorithm=Algorithm.EXPECTIMAX, heuristic=HeuristicScore.CORNER)
            # game.run(nbr_runs=runs, algorithm=Algorithm.EXPECTIMAX, heuristic=HeuristicScore.CORNERS)
            # game.run(nbr_runs=runs, algorithm=Algorithm.EXPECTIMAX, heuristic=HeuristicScore.SNAKE, continue_high_score=False)
            finished = True
        except Exception as e:
            logger.error("程序执行出错", exc_info=True)
            logger.info("程序异常退出，但浏览器窗口将保持打开状态")
        finally:
            print("程序执行完成")
   
if __name__ == '__main__':
    game_url = DEFAULT_GAME_URL
    if len(sys.argv) > 1:
        game_url = sys.argv[1]
    main(game_url)