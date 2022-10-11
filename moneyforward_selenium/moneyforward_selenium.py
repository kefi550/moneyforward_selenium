from selenium.webdriver import ChromeOptions, Remote
# from selenium.webdriver import Chrome
from selenium.webdriver.support.select import Select
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException
# import chromedriver_binary
from urllib.parse import urlparse
import argparse
import os
import re
import time


MONEYFORWARD_BASE_URL = "https://moneyforward.com"
MONEYFORWARD_USER = os.environ["MONEYFORWARD_USER"]
MONEYFORWARD_PASSWORD = os.environ["MONEYFORWARD_PASSWORD"]
SELENIUM_HOST = os.environ.get("SELENIUM_HOST", "127.0.0.1")
SELENIUM_PORT = os.environ.get("SELENIUM_PORT", "4444")

options = ChromeOptions()
options.add_argument("--headless")
options.add_argument("--disable-gpu")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")


def _chrome_profile(filepath: str = "./chrome_profile"):
    if not os.path.exists(filepath):
        os.mkdir(filepath)
    return filepath
    

# chrome_profile = _chrome_profile()
# driver = Chrome(
#         options=options,
# )
chrome_profile = "/home/seluser/.config/google-chrome/selenium"
options.add_argument(f"--user-data-dir={chrome_profile}")
driver = Remote(
    command_executor=f'http://{SELENIUM_HOST}:{SELENIUM_PORT}/wd/hub',
    desired_capabilities=options.to_capabilities(),
    options=options,
)
print("driver created")


def login(mf_user, mf_password):
    driver.get(MONEYFORWARD_BASE_URL)
    time.sleep(1)
    try:
        login_button = driver.find_element(By.CLASS_NAME, value='web-sign-in')
        login_button.find_element(By.TAG_NAME, 'a').click()
        time.sleep(2)
        url = urlparse(driver.current_url)
        driver.get(f"{url.scheme}://{url.hostname}/sign_in/email?{url.query}")
        driver.implicitly_wait(1)
        user_input = driver.find_element(By.NAME, value='mfid_user[email]')
        user_input.send_keys(mf_user)
        user_input.submit()
        driver.implicitly_wait(1)
        password_input = driver.find_element(By.NAME, value='mfid_user[password]')
        password_input.send_keys(mf_password)
        password_input.submit()
    except NoSuchElementException:
        # NoSuchElementExceptionの場合はログインフォームが出ない、すなわちログイン済みとしてpass
        pass
    print("logged in")


def close_driver():
    time.sleep(2)
    driver.quit()


def _update_mf_account(account: str, new_amount: float):
    driver.get(MONEYFORWARD_BASE_URL + "/accounts")
    group_select = Select(driver.find_element(By.CLASS_NAME, 'mf-floating-sub-account-box').find_element(By.TAG_NAME, 'select'))
    # 選択されているグループを覚えとく
    selected_group = group_select.first_selected_option.text
    # "グループ選択なし"グループに変更
    group_select.select_by_visible_text('グループ選択なし')
    driver.implicitly_wait(3)
    driver.find_element(By.LINK_TEXT, account).click()
    # 口座の総額
    asset_latest_text = driver.find_element(By.CLASS_NAME, 'bs-detail').find_element(By.TAG_NAME, 'section').find_element(By.TAG_NAME, 'h1').text
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
        return

    # 収入支出詳細
    in_out = driver.find_element(By.ID, "in_out")
    in_out.find_element(By.CLASS_NAME, "cf-new-btn").click()
    driver.implicitly_wait(3)
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
    driver.implicitly_wait(5)
    # 再描画されて要素を見失うのでリロードする
    driver.get(MONEYFORWARD_BASE_URL + "/accounts")
    driver.find_element(By.LINK_TEXT, account).click()
    in_out = driver.find_element(By.ID, "in_out")
    # ぜんぶ計算対象外とする(雑)
    for_calc = in_out.find_elements(By.CLASS_NAME, "icon-check")
    for payment in for_calc:
        payment.click()
    # 選択グループを元に戻す
    group_select = Select(driver.find_element(By.CLASS_NAME, 'mf-floating-sub-account-box').find_element(By.TAG_NAME, 'select'))
    group_select.select_by_visible_text(selected_group)


def update_mf_account(account: str, amount: float):
    login(MONEYFORWARD_USER, MONEYFORWARD_PASSWORD)
    _update_mf_account(account, amount)
    close_driver()
    print("finish")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("account", help='口座名')
    parser.add_argument("amount", type=float, help='新しい資産総額')
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()
    update_mf_account(args.account, args.amount)
