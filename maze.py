import database as db
import json
import os
import random
import requests
import time
from bs4 import BeautifulSoup
from discord_webhook import DiscordWebhook, DiscordEmbed

TELEGRAM_API = str(os.environ["TELEGRAM_API"])  # API do telegram para envio de logs
error_log = {}
session = time_start = time_elapsed = None  # Variáveis globais de sessão e tempo de execução


def send_error_log(local_time_elapsed):
    if error_log:
        log = "Maze API: " + str(round(local_time_elapsed, 2)) + "\n\n" + str(error_log).replace('_', ' ')
        requests.get(TELEGRAM_API + log)  # Chamada para API do telegram enviar o log


# Verifica se a execução ultrapassou o tempo limite
def timed_out():
    global time_elapsed
    global time_start

    time_elapsed = time.perf_counter() - time_start

    if time_elapsed >= 50:
        send_error_log(time_elapsed)
        return True

    return False


# Obtém um proxy aleatório de uma lista pré-definida para evitar banimento por IP
def get_random_proxy():
    try:
        proxies = list(db.get_proxies().to_dict().values())
        random_proxy = random.choice(proxies)
        proxy = {'http': random_proxy, 'https': random_proxy}

        return proxy

    except Exception as error:
        error_log['get random proxy'] = str(error)
        return None


# Obtém um header aleatório de uma lista pré-definida para evitar banimento por IP
def get_random_header():
    try:
        header_list = list(db.get_headers().to_dict().values())
        random_header = random.choice(header_list)
        return random_header

    except Exception as error:
        error_log['get random header'] = str(error)
        return 'Mozilla/5.0'


# Cria uma sessão com um header aleatório
def create_new_session():
    try:
        global session
        session = requests.Session()
        session.headers.update({'User-Agent': get_random_header()})

    except Exception as error:
        error_log['create new session'] = str(error)


# Verifica resposta do webhook discord
def check_response(response):
    if "200" not in str(response[0]):
        error_log['check response'] = 'Erro ao executar o discord webhook'


# Envia mensagem com informações do produto no Discord
def send_message(webhook_info, product_info):
    try:
        webhook_url = webhook_info.get('webhook_url')
        webhook_color = webhook_info.get('color')
        is_restock = webhook_info.get('is_restock')
        url = product_info.get('url')

        webhook = DiscordWebhook(url=webhook_url)
        message = DiscordEmbed(title=product_info.get('name'), url=url, color=webhook_color)

        message.add_embed_field(name='Preço', value=product_info.get('price'), inline=False)

        # Verifica se o produto já existe no banco de dados e captura os tamanhos disponíveis
        if is_restock:
            out_of_stock = True
            sizes = get_sizes(url)

            if sizes:
                sizes = sizes.get('sizes')

                for size in sizes.keys():
                    message.add_embed_field(name=f'> Size {size}', value=f'[Estoque: {sizes.get(size)}]({url})', inline=False)
                    out_of_stock = False

            # Cancela o envio da mensagem em caso de falta de estoque
            if out_of_stock:
                return

        message.set_thumbnail(url=product_info.get('img'))
        message.set_footer(text='** Clique em "Trust this Domain" para garantir acesso mais rápido ao link ')
        message.set_timestamp()

        webhook.add_embed(message)
        response = webhook.execute()
        check_response(response)

    except Exception as error:
        error_log['send product'] = str(error)


# Ordena os tamanhos do produto por ordem crescente
def sort_size_grid(size_grid):
    try:
        sorted_size_grid = {}

        sizes = list(size_grid.keys())
        sizes.sort()

        for size in sizes:
            sorted_size_grid[size] = size_grid.get(size)

        return sorted_size_grid

    except Exception as error:
        error_log['sort size grid'] = str(error)
        return size_grid


# Consulta os tamanhos disponíveis do produto
def get_sizes(url):
    try:
        size_grid = {}
        product_source = get_product_source(url)
        sizes_source = BeautifulSoup(product_source, features="html.parser").find("input", {"id": "json-detail"})  # Encontra o elemento da página que contém os tamanhos

        # Retorna a função se não existir tamanhos disponíveis
        if not sizes_source:
            return False

        sizes_grid = json.loads(sizes_source.get('value'))['Variations']

        for size in sizes_grid:
            size_name = size['Name']
            size_stock = size['Sku']['Stock']

            if size_stock > 0:
                size_grid[size_name] = size_stock

        if not size_grid:
            return None

        size_info = {'source': product_source, 'sizes': sort_size_grid(size_grid)}
        return size_info

    except Exception as error:
        error_log['get sizes'] = str(error)
        return False


# Insere produto no banco de dados para monitoramento
def insert_product(id, url, category):
    try:
        for document in [category, "history", "snkrs"]:
            db.insert_product(id, url, document)

    except Exception as error:
        error_log['insert product'] = str(error)


# Define as características da mensagem com base no tipo de produto
def get_webhook(product_id, products_history):
    try:
        webhook_url = str(os.environ["WEBHOOK_MONITOR"])
        is_restock = False
        color = 15158332  # Cor vermelha em decimal para indicar um novo produto

        if product_id in products_history:
            webhook_url = str(os.environ["WEBHOOK_RESTOCK"])
            is_restock = True
            color = 16776960  # Cor amarela em decimal para indicar um restock

        webhook_info = {'webhook_url': webhook_url, 'is_restock': is_restock, 'color': color}

        return webhook_info

    except Exception as error:
        error_log['get webhook'] = str(error)
        return {'webhook_url': webhook_url, 'is_restock': False, 'color': color}


# Função para trocar um produto de tabela
def swap_restock(db_documents, id, url):
    try:
        db.insert_product(id, url, db_documents[0])  # Insere o produto na lista de restock
        db.delete_product(id, db_documents[1])  # Retira o produto da lista de lançamentos

    except Exception as error:
        error_log['swap restock'] = str(error)


# Captura a página de um produto utilizando proxy para evitar bloqueios
def get_product_source_proxy(url):
    try:
        for _ in range(3):
            try:
                source = session.get(url, proxies=get_random_proxy(), timeout=5).content
                return source

            except:
                continue

        raise Exception('Não foi possível obter o source com proxy')

    except Exception as error:
        error_url = url.replace('https://www.maze.com.br/', '').replace('produto/', '')
        error_log['get product source - ' + error_url] = str(error)
        return ''


# Captura a página de um produto
def get_product_source(url):
    try:
        source = session.get(url, timeout=5).content
        return source

    except:
        return get_product_source_proxy(url)


# Captura a página da lista de produtos utilizando proxy para evitar bloqueios
def get_source_proxy(url, category):
    try:
        for _ in range(3):
            try:
                source = session.get(url, proxies=get_random_proxy(), timeout=5).content
                return source

            except:
                continue

        raise Exception('Não foi possível obter o source com proxy')

    except Exception as error:
        error_log['get source ' + category] = str(error)
        return ''


# Captura a página da lista de produtos
def get_source():
    try:
        base_url = 'https://www.maze.com.br/product/getproducts/?pageNumber=1&pageSize=60&keyWord={keyword}'
        sources = {'jordan': '', 'dunk': '', 'yeezy': '', 'air%20force': '', 'nike%20stussy': ''}  # Keywords que serão pesquisadas

        # Percorre cada keyword para capturar as páginas
        for source_keyword in sources.keys():
            try:
                url = base_url.format(keyword=source_keyword)
                category = source_keyword.replace('%20', '')

                source = session.get(url, timeout=5).content
                sources[source_keyword] = source

            except:
                sources[source_keyword] = get_source_proxy(url, category)
                continue

        return sources

    except Exception as error:
        error_log['get source'] = str(error)
        return {}


# Verifica se uma numeração específica está disponívei
def has_stock(data_exhausted):
    if data_exhausted == "True":
        return False

    return True


# Consolida os produtos identificados no site para montar a mensagem que será enviada no Discord
def get_products(source):
    try:
        products = {}
        product_grid = BeautifulSoup(source, features="html.parser").findAll('div', {'class': 'product-in-card'})

        for product in product_grid:
            product_id = product.meta.get('content')

            if product_id not in products.keys():
                products[product_id] = {
                    'name': product.a.get('title').title(),
                    'url': "https://www.maze.com.br" + product.a.get('href'),
                    'img': "https:" + product.img.get('data-src'),
                    'price': "R$" + product.find("meta", {"itemprop": "price"}).get('content').replace(".", ","),
                    'has_stock': has_stock(product.get('data-exhausted'))
                }

        return products

    except Exception as error:
        error_log['get products'] = str(error)
        return None


# Verifica se o produto já está na lista de produtos encontrada para evitar duplicados
def is_new_product(product_id, products):
    try:
        if product_id in products:
            return False

        return True

    except Exception as error:
        error_log['is new product'] = str(error)
        return False


# Atualiza os produtos que entraram/saíram do estoque
def update_products(products, category):
    try:
        if not products:
            raise Exception(f'{category} - Nenhum produto encontrado')

        category_on = category + '_on'
        category_off = category + '_off'

        products_on = db.get_products(category_on).to_dict()
        products_off = db.get_products(category_off).to_dict()

        lancamentos = db.get_products("lancamentos").to_dict()
        bugados = db.get_products("bugados").to_dict().keys()  # Lista de produtos que constam em estoque mas não estão (problema do site)

        for product_id in products.keys():
            if timed_out():
                return True

            # Não itera nos produtos que estão com problema
            if product_id in bugados:
                continue

            products_history = db.get_products('history').to_dict().keys()
            product_info = products.get(product_id)
            product_url = product_info.get('url')
            webhook_url = get_webhook(product_id, products_history)

            if is_new_product(product_id, products_history):
                send_message(webhook_url, product_info)
                insert_product(product_id, product_url, category_on)
                continue

            if product_info.get('has_stock'):
                if not products_on.get(product_id):
                    if not lancamentos.get(product_id):
                        send_message(webhook_url, product_info)
                    if products_off.get(product_id):
                        swap_restock([category_on, category_off], product_id, product_url)
                    else:
                        db.insert_product(product_id, product_url, category_on)

                continue

            else:
                if not products_off.get(product_id):
                    if products_on.get(product_id):
                        swap_restock([category_off, category_on], product_id, product_url)
                    else:
                        db.insert_product(product_id, product_url, category_on)

                continue

        for product_id in products_off.keys():
            if not products.get(product_id):
                swap_restock(["restock_off", category_off], product_id, products_off.get(product_id))

    except Exception as error:
        error_log[f'{category} - update products'] = str(error)
        return None


# Função principal que faz as chamadas para as outras funções
def maze():
    try:
        sources = get_source()

        for keyword in sources.keys():
            if timed_out():
                return True

            source = sources.get(keyword)
            products = get_products(source)
            category = keyword.replace('%20', '')

            if update_products(products, category):
                return True

        return False

    except Exception as error:
        requests.get(TELEGRAM_API + "Maze API - main: " + str(error))
        return False


# Função chamada no Google Cloud Functions
def main(self):
    global time_start
    time_start = time.perf_counter()
    error_log.clear()

    # Executa a varredura no site até finalizar ou alcançar o tempo máximo de execução (timeout)
    while True:
        create_new_session()

        if maze():
            return 'ok'

        if timed_out():
            return 'ok'

        time.sleep(5)

        if timed_out():
            return 'ok'
