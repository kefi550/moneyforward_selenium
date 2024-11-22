from selenium.webdriver import Remote
from selenium.webdriver import ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.select import Select
import os
import re
import time


MONEYFORWARD_BASE_URL = "https://moneyforward.com"
MONEYFORWARD_USER = os.environ["MONEYFORWARD_USER"]
MONEYFORWARD_PASSWORD = os.environ["MONEYFORWARD_PASSWORD"]
SELENIUM_HOST = os.environ.get("SELENIUM_HOST", "127.0.0.1")
SELENIUM_PORT = os.environ.get("SELENIUM_PORT", "4444")
CHROME_PROFILE_PATH = os.environ.get("CHROME_PROFILE_PATH", "/tmp/moneyforward-selenium")


class MoneyForwardScraper:
    def __init__(self, mf_user, mf_password):
        self.create_driver()
        self.login(mf_user, mf_password)
        self.previous_selected_group = self.get_current_group()

    def __del__(self):
        self.change_mf_group(self.previous_selected_group)
        self.close_driver()

    def create_driver(self):
        options = ChromeOptions()
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        # options.add_argument("--headless")
        options.add_argument('--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/102.0.0.0 Safari/537.36')
        options.add_argument(f"--user-data-dir={CHROME_PROFILE_PATH}")
        self.driver = Remote(
            command_executor=f'http://{SELENIUM_HOST}:{SELENIUM_PORT}/wd/hub',
            options=options,
        )
        print("driver created")

    def close_driver(self):
        self.driver.quit()
        print("driver closed")

    def is_logined(self):
        self.driver.get(MONEYFORWARD_BASE_URL)
        time.sleep(1)
        mfid = self.driver.get_cookie("identification_code")
        return mfid is not None

    def login(self, mf_user, mf_password):
        if self.is_logined():
            print("already logged in")
            return
        self.driver.get(MONEYFORWARD_BASE_URL + "/sign_in")
        time.sleep(1)
        user_input = self.driver.find_element(By.NAME, value='mfid_user[email]')
        user_input.send_keys(mf_user)
        user_input.submit()
        time.sleep(1)
        password_input = self.driver.find_element(By.NAME, value='mfid_user[password]')
        password_input.send_keys(mf_password)
        password_input.submit()
        print("logged in")

    def _update_account_amount(self, account: str, new_amount: float):
        self.driver.get(MONEYFORWARD_BASE_URL + "/accounts")
        self.driver.find_element(By.LINK_TEXT, account).click()
        # 口座の総額
        asset_latest_text = self.driver.find_element(By.CLASS_NAME, 'bs-detail').find_element(By.TAG_NAME, 'section').find_element(By.TAG_NAME, 'h1').text
        latest_amount = re.findall(r'[0-9]+', asset_latest_text.replace(',', ''))
        if len(latest_amount) != 1:
            raise Exception(f'最新の資産総額の取得に失敗しました。取得したテキスト: {asset_latest_text}')
        latest_amount = int(latest_amount[0])
        print(f"現状の資産総額: {latest_amount}")
        print(f"新しい資産総額: {new_amount}")

        # 現在の資産総額と新たな資産総額の差額を計算
        amount_diff = int(new_amount - latest_amount)
        print(f"資産総額diff: {amount_diff}")
        if amount_diff == 0:
            print("差分なしにより何もせず終了")
        else:
            # 収入支出詳細
            in_out = self.driver.find_element(By.ID, "in_out")
            in_out.find_element(By.CLASS_NAME, "cf-new-btn").click()
            time.sleep(3)
            # 手入力モーダル
            modal = in_out.find_element(By.ID, "user_asset_act_new")
            # 差額がプラスなら収入、マイナスなら支出として入力
            if amount_diff > 0:
                modal.find_element(By.CLASS_NAME, "plus-payment").click()
            else:
                amount_diff = abs(amount_diff)
                modal.find_element(By.CLASS_NAME, "minus-payment").click()
            modal.find_element(By.ID, "appendedPrependedInput").send_keys(amount_diff)
            modal.find_element(By.CLASS_NAME, "submit-box").click()
            time.sleep(5)
            # 再描画されて要素を見失うのでリロードする
            self.driver.get(MONEYFORWARD_BASE_URL + "/accounts")
            self.driver.find_element(By.LINK_TEXT, account).click()
            in_out = self.driver.find_element(By.ID, "in_out")
            # ぜんぶ計算対象外とする(雑)
            for_calc = in_out.find_elements(By.CLASS_NAME, "icon-check")
            for payment in for_calc:
                payment.click()
            print(f"新しい資産総額 {new_amount} の登録完了")

    def get_current_group(self):
        group_select = Select(self.driver.find_element(By.CLASS_NAME, 'mf-floating-sub-account-box').find_element(By.TAG_NAME, 'select'))
        current_group = group_select.first_selected_option.text
        return current_group

    def change_mf_group(self, group_name: str):
        group_select = Select(self.driver.find_element(By.CLASS_NAME, 'mf-floating-sub-account-box').find_element(By.TAG_NAME, 'select'))
        group_select.select_by_visible_text(group_name)
        time.sleep(3)


def update_mf_account(account: str, amount: float):
    mf = MoneyForwardScraper(MONEYFORWARD_USER, MONEYFORWARD_PASSWORD)
    mf.change_mf_group('グループ選択なし')
    mf._update_account_amount(account, amount)
