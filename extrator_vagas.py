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
from datetime import datetime

# ==========================================
# CONFIGURAÇÕES
# ==========================================
QTD_PAGINAS_PARA_LER = 20  
NOME_ARQUIVO = 'vagas_apinfo.xlsx'

def iniciar_driver():
    print("--- Iniciando o Navegador Controlado (Headless) ---")
    chrome_options = Options()
    # OBRIGATÓRIO NA NUVEM:
    chrome_options.add_argument("--headless") 
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    
    servico = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=servico, options=chrome_options)
    return driver

def extrair_vagas_selenium():
    driver = iniciar_driver()
    todas_as_vagas = []
    
    try:
        # 1. ACESSA A PÁGINA
        print("Acessando APInfo...")
        driver.get("https://www.apinfo.com/apinfo/inc/list4.cfm")
        
        # 2. FAZ A PESQUISA
        print("Realizando pesquisa...")
        wait = WebDriverWait(driver, 10)
        
        # Clica no botão pesquisar
        botao_pesquisa = wait.until(EC.element_to_be_clickable((By.XPATH, "//input[@type='submit']")))
        botao_pesquisa.click()
        
        # 3. LOOP DE PAGINAÇÃO
        for pagina in range(1, QTD_PAGINAS_PARA_LER + 1):
            print(f"\n>>> Lendo PÁGINA {pagina}...")
            
            # Espera a tabela carregar para garantir que a página mudou
            time.sleep(3) 
            
            # --- EXTRAÇÃO ---
            site = BeautifulSoup(driver.page_source, 'html.parser')
            texto_bruto = site.get_text()
            linhas = texto_bruto.split('\n')
            
            vagas_pagina = []
            buffer_texto = []
            
            for linha in linhas:
                linha_limpa = linha.strip()
                if not linha_limpa: continue
                
                if "Código" in linha_limpa and ":" in linha_limpa:
                    cod = linha_limpa
                    try: cod = linha_limpa.split(':')[1].split('-')[0].strip()
                    except: pass
                    
                    if buffer_texto:
                        vagas_pagina.append({
                            'Data_Coleta': datetime.now().strftime("%d/%m/%Y"),
                            'ID_Vaga': cod,
                            'Titulo_Empresa': buffer_texto[0],
                            'Descricao': " | ".join(buffer_texto[1:]),
                            'Pagina': pagina
                        })
                    buffer_texto = []
                else:
                    buffer_texto.append(linha_limpa)
            
            print(f"    -> Vagas encontradas: {len(vagas_pagina)}")
            todas_as_vagas.extend(vagas_pagina)
            
            if pagina == QTD_PAGINAS_PARA_LER:
                print("Fim da meta de páginas.")
                break
                
            # --- MUDANÇA DE PÁGINA (TÉCNICA BLINDADA) ---
            try:
                # 1. Rola até o final da página para garantir que o input está visível
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1)

                # 2. Encontra o campo de página
                campo_pagina = driver.find_element(By.NAME, "pag")
                
                # 3. A MÁGICA: Usa JavaScript para forçar o valor (evita erro 'invalid element state')
                nova_pagina = str(pagina + 1)
                driver.execute_script("arguments[0].value = arguments[1];", campo_pagina, nova_pagina)
                
                # 4. Clica no botão OK via JavaScript também (mais seguro)
                botao_ok = driver.find_element(By.XPATH, "//input[@value='OK']")
                driver.execute_script("arguments[0].click();", botao_ok)
                
            except Exception as e:
                print(f"    [!] Erro ao mudar de página: {e}")
                print("    Tentando continuar...")
                break
                
    except Exception as e:
        print(f"Erro fatal: {e}")
    finally:
        print("Fechando navegador...")
        driver.quit()
        
    return todas_as_vagas

def salvar_excel(dados):
    if not dados: 
        print("Nenhuma vaga coletada.")
        return

    df = pd.DataFrame(dados)
    df.drop_duplicates(subset=['ID_Vaga'], inplace=True)
    
    if os.path.exists(NOME_ARQUIVO):
        try:
            antigo = pd.read_excel(NOME_ARQUIVO)
            antigo['ID_Vaga'] = antigo['ID_Vaga'].astype(str)
            df['ID_Vaga'] = df['ID_Vaga'].astype(str)
            
            novas = df[~df['ID_Vaga'].isin(antigo['ID_Vaga'])]
            print(f"\nRELATÓRIO: {len(dados)} lidas. {len(novas)} NOVAS salvas.")
            
            if not novas.empty:
                pd.concat([antigo, novas]).to_excel(NOME_ARQUIVO, index=False)
            else:
                print("Excel já estava atualizado.")
        except:
            df.to_excel(NOME_ARQUIVO, index=False)
    else:
        df.to_excel(NOME_ARQUIVO, index=False)
        print(f"Arquivo criado com {len(df)} vagas.")

if __name__ == "__main__":
    dados = extrair_vagas_selenium()
    salvar_excel(dados)