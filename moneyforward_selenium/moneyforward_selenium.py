import os
import re
import datetime
from dataclasses import dataclass

from selenium.webdriver import Remote
from selenium.webdriver import ChromeOptions
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support.select import Select
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


MONEYFORWARD_BASE_URL = "https://moneyforward.com"
SELENIUM_HOST = os.environ.get("SELENIUM_HOST", "127.0.0.1")
SELENIUM_PORT = os.environ.get("SELENIUM_PORT", "4444")
CHROME_PROFILE_PATH = os.environ.get("CHROME_PROFILE_PATH", "/tmp/moneyforward-selenium")


@dataclass
class Cashflow:
    id: int
    calc: bool
    date: datetime.date
    fiscal_year: int
    fiscal_month: int
    content: str
    amount: int
    note: str
    lcategory: str
    mcategory: str
    memo: str


@dataclass
class Budget:
    lcategory: str
    budget: int
    group_name: str


class MoneyForwardScraper:
    def __init__(self, user, password, group_name=None):
        self.create_driver()
        self.login(user, password)
        self.group_name = self.previous_selected_group = self.get_current_group()
        # グループが指定されている場合は変更
        if group_name is not None and group_name != self.previous_selected_group:
            self.change_mf_group(group_name)
            self.group_name = group_name

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            self.change_mf_group(self.previous_selected_group)
        finally:
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
        if self.driver is not None:
            self.driver.quit()
            print("driver closed")

    def is_logined(self):
        self.driver.get(MONEYFORWARD_BASE_URL)
        mfid = self.driver.get_cookie("identification_code")
        return mfid is not None

    def login(self, mf_user, mf_password):
        if self.is_logined():
            print("already logged in")
            return
        self.driver.get(MONEYFORWARD_BASE_URL + "/sign_in")
        WebDriverWait(self.driver, 5).until(EC.presence_of_element_located((By.NAME, 'mfid_user[email]')))
        user_input = self.driver.find_element(By.NAME, value='mfid_user[email]')
        user_input.send_keys(mf_user)
        user_input.submit()
        WebDriverWait(self.driver, 5).until(EC.presence_of_element_located((By.NAME, 'mfid_user[password]')))
        password_input = self.driver.find_element(By.NAME, value='mfid_user[password]')
        password_input.send_keys(mf_password)
        password_input.submit()
        print("logged in")

    def get_current_group(self):
        group_select = Select(self.driver.find_element(By.CLASS_NAME, 'mf-floating-sub-account-box').find_element(By.TAG_NAME, 'select'))
        current_group = group_select.first_selected_option.text
        return current_group

    def change_mf_group(self, group_name: str):
        group_select = Select(self.driver.find_element(By.CLASS_NAME, 'mf-floating-sub-account-box').find_element(By.TAG_NAME, 'select'))
        try:
            group_select.select_by_visible_text(group_name)
            print(f"グループ {group_name} に変更しました")
        except NoSuchElementException:
            raise Exception(f"グループ {group_name} が見つかりませんでした")

    def update_account_amount(self, account: str, new_amount: float):
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
            WebDriverWait(self.driver, 5).until(EC.presence_of_element_located((By.ID, "user_asset_act_new")))
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
            # 再描画されて要素を見失うのでリロードする
            self.driver.get(MONEYFORWARD_BASE_URL + "/accounts")
            self.driver.find_element(By.LINK_TEXT, account).click()
            in_out = self.driver.find_element(By.ID, "in_out")
            # ぜんぶ計算対象外とする(雑)
            for_calc = in_out.find_elements(By.CLASS_NAME, "icon-check")
            for payment in for_calc:
                payment.click()
            print(f"新しい資産総額 {new_amount} の登録完了")

    def change_fiscal_month(self, year: int, month: int):
        self.driver.get(MONEYFORWARD_BASE_URL + "/cf")
        # ちょっと下にスクロール
        self.driver.execute_script("window.scrollBy(0, 1000)")
        year_selector_button = self.driver.find_element(By.CLASS_NAME, 'uikit-year-month-select-dropdown')
        year_selector_button.click()
        year_selector = self.driver.find_elements(By.CLASS_NAME, 'uikit-year-month-select-dropdown-year-part')
        for div in year_selector:
            if div.text == str(year):
                break
        actions = ActionChains(self.driver)
        actions.move_to_element(div).perform()
        print(f"{year}年を選択した")
        WebDriverWait(self.driver, 5).until(EC.presence_of_element_located((By.CLASS_NAME, 'uikit-year-month-select-dropdown-month-part')))
        month_dropdown = div.find_element(By.CLASS_NAME, 'uikit-year-month-select-dropdown-month-part')
        month_button = month_dropdown.find_element(By.XPATH, f"a[@data-month=\"{month}\"]")
        month_button.click()
        print(f"{month}月を選択した")

    def get_cashflows_of_fiscal_month(self, fiscal_year: int, fiscal_month: int):
        cashflows = []
        self.change_fiscal_month(fiscal_year, fiscal_month)
        cf_detail_table = self.driver.find_element(By.ID, 'cf-detail-table')
        for row in cf_detail_table.find_element(By.TAG_NAME, 'tbody').find_elements(By.TAG_NAME, 'tr'):
            calc = True
            if 'mf-grayout' in row.get_attribute('class'):
                calc = False

            cells = row.find_elements(By.TAG_NAME, 'td')
            date_id = cells[1].get_attribute('data-table-sortable-value')
            date = date_id.split('-')[0]
            id = int(date_id.split('-')[1])
            content = cells[2].find_element(By.TAG_NAME, 'span').text
            amount = cells[3].find_element(By.TAG_NAME, 'span').text.replace(',', '')
            if cells[4].find_elements(By.CLASS_NAME, 'transfer_account_box'):
                if int(amount) >= 0:
                    note = cells[4].find_element(By.CLASS_NAME, 'transfer_account_box').text
                else:
                    note = cells[4].text
            else:
                note = cells[4].text
            if calc:
                lcategory = cells[5].find_element(By.TAG_NAME, 'a').text
                mcategory = cells[6].find_element(By.TAG_NAME, 'a').text
            memo = cells[7].find_element(By.TAG_NAME, 'span').text

            print(f"{date} {content} {amount} {note} {lcategory} {mcategory}")

            cashflow = Cashflow(
                id=id,
                calc=calc,
                date=datetime.datetime.strptime(date, '%Y/%m/%d').date(),
                fiscal_year=fiscal_year,
                fiscal_month=fiscal_month,
                content=content,
                amount=int(amount),
                note=note,
                lcategory=lcategory,
                mcategory=mcategory,
                memo=memo,
            )
            cashflows.append(cashflow)
        return cashflows

    def get_budgets_of_group(self):
        self.driver.get(MONEYFORWARD_BASE_URL + "/spending_targets/edit")
        WebDriverWait(self.driver, 5).until(EC.presence_of_element_located((By.CLASS_NAME, 'budget_detail')))
        budget_div = self.driver.find_element(By.CLASS_NAME, 'budget_detail')
        budget_table = budget_div.find_element(By.TAG_NAME, 'table')
        budgets = []
        for row in budget_table.find_element(By.TAG_NAME, 'tbody').find_elements(By.CSS_SELECTOR, 'tr.large_category'):
            lcategory = row.find_element(By.TAG_NAME, 'th').text
            budget = int(row.find_element(By.CSS_SELECTOR, 'input.large_category_amount').get_attribute('value'))
            b = Budget(
                lcategory=lcategory,
                budget=budget,
                group_name=self.group_name,
            )
            budgets.append(b)
        return budgets
