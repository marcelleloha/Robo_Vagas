from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import pandas as pd
import time
import os
import re  # Biblioteca de Expressões Regulares (para achar datas e números)
from datetime import datetime

# ==========================================
# ⚙️ CONFIGURAÇÕES
# ==========================================
QTD_PAGINAS_PARA_LER = 20
NOME_ARQUIVO = 'vagas_apinfo.xlsx'

# ==========================================
# 1. INICIALIZAÇÃO DO ROBÔ
# ==========================================
def iniciar_driver():
    print("--- Iniciando o Navegador Controlado ---")
    chrome_options = Options()
    # Se quiser rodar sem abrir a janela, tire o # da linha abaixo:
    # chrome_options.add_argument("--headless") 
    
    # Configurações para estabilidade (evita erros em servidores/docker)
    chrome_options.add_argument("--headless") # OBRIGATÓRIO NA NUVEM
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    
    servico = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=servico, options=chrome_options)
    return driver

# ==========================================
# 2. EXTRAÇÃO INTELIGENTE (COM REGEX)
# ==========================================
def extrair_vagas_selenium():
    driver = iniciar_driver()
    todas_as_vagas = []
    
    # Lista de textos inúteis para ignorar
    LIXO_VISUAL = [
        "Politica de Cookies"
    ]
    
    try:
        print("Acessando APInfo...")
        driver.get("https://www.apinfo.com/apinfo/inc/list4.cfm")
        
        print("Realizando pesquisa...")
        wait = WebDriverWait(driver, 10)
        # Clica no botão de pesquisar
        botao_pesquisa = wait.until(EC.element_to_be_clickable((By.XPATH, "//input[@type='submit']")))
        botao_pesquisa.click()
        
        for pagina in range(1, QTD_PAGINAS_PARA_LER + 1):
            print(f"\n>>> Lendo PÁGINA {pagina}...")
            time.sleep(3) # Espera carregar
            
            site = BeautifulSoup(driver.page_source, 'html.parser')
            texto_bruto = site.get_text()
            linhas = texto_bruto.split('\n')
            
            vagas_pagina = []
            buffer_texto = []
            
            for linha in linhas:
                linha_limpa = linha.strip()
                if not linha_limpa: continue
                
                # A. FILTRO DE LIXO
                if any(lixo.lower() in linha_limpa.lower() for lixo in LIXO_VISUAL):
                    continue

                # B. IDENTIFICAÇÃO DO BLOCO DA VAGA (Quando acha "Código :")
                if "Código" in linha_limpa and ":" in linha_limpa:
                    try:
                        # Limpeza do ID (Pega só números)
                        numeros = re.findall(r'\d+', linha_limpa)
                        cod = numeros[0] if numeros else "SEM_CODIGO"
                        
                        titulo = "Não Identificado"
                        info_local_data = "Não Informado"
                        descricao_lista = buffer_texto
                        
                        if buffer_texto:
                            primeira_linha = buffer_texto[0]
                            
                            # --- LÓGICA DE SEGURANÇA (REGEX) ---
                            # Verifica se a linha termina com data (ex: 14/01/26)
                            # Padrão: dia/mes/ano no final da string ($)
                            tem_data_no_fim = re.search(r'\d{2}/\d{2}/\d{2}$', primeira_linha.strip())
                            
                            if tem_data_no_fim:
                                # Achamos a linha de LOCAL/DATA
                                info_local_data = primeira_linha
                                if len(buffer_texto) > 1:
                                    titulo = buffer_texto[1] # Título é a próxima linha
                                    descricao_lista = buffer_texto[2:]
                                else:
                                    titulo = "Verificar Info Auxiliar" # Caso raro
                                    descricao_lista = buffer_texto[1:]
                            else:
                                # A linha não parece data, então deve ser o Título
                                titulo = primeira_linha
                                descricao_lista = buffer_texto[1:]

                        # Salva a vaga com TODAS as informações (sem deletar nada)
                        vagas_pagina.append({
                            'Data_Coleta': datetime.now().strftime("%d/%m/%Y"),
                            'ID_Vaga': cod,
                            'Titulo_Empresa': titulo,
                            'Info_Auxiliar': info_local_data,   # Guarda Local/Data separado
                            'Descricao': " | ".join(descricao_lista),
                            'Conteudo_Completo': " || ".join(buffer_texto), # BACKUP DE SEGURANÇA
                            'Pagina': pagina
                        })
                    except Exception as e:
                        print(f"Erro ao processar vaga {cod}: {e}")
                        
                    buffer_texto = [] # Limpa para a próxima
                else:
                    buffer_texto.append(linha_limpa)
            
            print(f"    -> Vagas encontradas: {len(vagas_pagina)}")
            todas_as_vagas.extend(vagas_pagina)
            
            if pagina == QTD_PAGINAS_PARA_LER:
                print("Meta atingida.")
                break
            
            # --- PAGINAÇÃO BLINDADA (JavaScript) ---
            try:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1)
                campo_pagina = driver.find_element(By.NAME, "pag")
                # Injeta o número da próxima página direto no HTML
                driver.execute_script("arguments[0].value = arguments[1];", campo_pagina, str(pagina + 1))
                botao_ok = driver.find_element(By.XPATH, "//input[@value='OK']")
                # Clica via código
                driver.execute_script("arguments[0].click();", botao_ok)
            except Exception as e:
                print(f"    [!] Erro ao mudar de página: {e}")
                break
                
    except Exception as e:
        print(f"Erro fatal: {e}")
    finally:
        print("Fechando navegador...")
        driver.quit()
        
    return todas_as_vagas

# ==========================================
# 3. TRATAMENTO E LIMPEZA (PANDAS)
# ==========================================
def tratar_dados(df):
    print("--- Processando dados... ---")
    if df.empty: return df

    # --- FILTRO: REMOVER CABEÇALHOS DO SITE ---
    filtro_lixo = "APinfo - O ponto de encontro"
    
    # .copy() garante que estamos trabalhando num objeto novo
    df = df[~df['Titulo_Empresa'].str.contains(filtro_lixo, case=False, na=False)].copy()
    
    # Limpeza visual da descrição
    df['Descricao'] = df['Descricao'].str.replace(' | ', '\n', regex=False)
    
    # 1. Identificar Modelo de Trabalho
    def checar_modelo(row):
        # MUDANÇA AQUI:
        # Agora concatenamos também o str(row['Info_Auxiliar']) na busca.
        # Assim, se estiver escrito "Home Office" lá, o robô pega.
        texto = (str(row['Descricao']) + str(row['Titulo_Empresa']) + str(row['Info_Auxiliar'])).lower()
        
        if 'home office' in texto or 'remoto' in texto or '100% remoto' in texto:
            return 'Remoto'
        elif 'híbrido' in texto or 'hibrido' in texto:
            return 'Híbrido'
        return 'Presencial/Outros'
    
    df['Modelo'] = df.apply(checar_modelo, axis=1)

    # 2. Estimativa de Nível
    def checar_nivel(texto):
        texto = str(texto).lower()
        if 'sênior' in texto or 'senior' in texto or 'sr.' in texto: return 'Sênior'
        if 'pleno' in texto or 'pl.' in texto: return 'Pleno'
        if 'júnior' in texto or 'junior' in texto or 'jr.' in texto: return 'Júnior'
        if 'estágio' in texto or 'estagiario' in texto: return 'Estágio'
        return 'Indefinido'

    df['Nivel'] = df['Titulo_Empresa'].apply(checar_nivel)
    
    # 3. Organizar Colunas
    colunas_desejadas = [
        'Data_Coleta', 'ID_Vaga', 'Titulo_Empresa', 'Nivel', 'Modelo', 
        'Info_Auxiliar', 'Descricao', 'Conteudo_Completo', 'Pagina'
    ]
    colunas_finais = [c for c in colunas_desejadas if c in df.columns]
    
    return df[colunas_finais]

# ==========================================
# 4. SALVAMENTO (EXCEL)
# ==========================================
def salvar_excel(dados):
    if not dados: return
    
    df_novo = pd.DataFrame(dados)
    df_novo = tratar_dados(df_novo)
    
    # Remove duplicatas baseadas no ID da vaga
    df_novo.drop_duplicates(subset=['ID_Vaga'], inplace=True)
    
    if os.path.exists(NOME_ARQUIVO):
        try:
            df_antigo = pd.read_excel(NOME_ARQUIVO)
            # Garante que ID é texto para comparar certo
            df_antigo['ID_Vaga'] = df_antigo['ID_Vaga'].astype(str)
            df_novo['ID_Vaga'] = df_novo['ID_Vaga'].astype(str)
            
            # Pega só o que não tem no arquivo antigo
            novas = df_novo[~df_novo['ID_Vaga'].isin(df_antigo['ID_Vaga'])]
            
            print(f"\nRELATORIO: {len(dados)} vagas processadas. {len(novas)} sao INEDITAS.")
            
            if not novas.empty:
                df_final = pd.concat([df_antigo, novas], ignore_index=True)
                df_final.to_excel(NOME_ARQUIVO, index=False)
                print("[OK] Excel atualizado com sucesso!")
            else:
                print("Tudo atualizado. Sem novidades.")
        except PermissionError:
            print("\n[ERRO CRITICO] O Excel esta aberto!")
            print("   Feche o arquivo 'vagas_apinfo.xlsx' e rode novamente.")
    else:
        df_novo.to_excel(NOME_ARQUIVO, index=False)
        print(f"[OK] Arquivo criado com {len(df_novo)} vagas.")

# ==========================================
# EXECUÇÃO
# ==========================================
if __name__ == "__main__":
    # 1. Extrai
    dados_brutos = extrair_vagas_selenium()
    # 2. Trata e Salva
    salvar_excel(dados_brutos)