# VideoML Editor

**Software de análise e anotação de vídeos médicos para avaliação de exames de fluoroscopia**

---

## Sobre o Projeto

O **VideoML Editor** é um software de análise de vídeos médicos criado para auxiliar médicos e fonoaudiólogos na avaliação de exames de fluoroscopia do tipo **VFSS** (Videofluoroscopic Swallowing Study) utilizando o método **ASPEKT**.

A ferramenta permite carregar vídeos nos formatos AVI e MP4, navegar frame a frame e criar anotações estruturadas diretamente sobre o vídeo. O software oferece recursos para:

- Criação e manipulação de **pontos**, **retas**, **ângulos** e **máscaras** (seleção livre e pincel)
- Registro visual de eventos clínicos relevantes
- Exportação de máscaras binárias para uso em pipelines de Machine Learning
- Organização hierárquica de frames de interesse e geometrias associadas

---

## Público-Alvo

| Perfil | Uso |
|--------|-----|
| **Profissionais de saúde** | Análises temporais e espaciais durante avaliação clínica da deglutição |
| **Pesquisadores** | Estudos quantitativos da deglutição na área de saúde |
| **Estudantes** | Anotações sistemáticas em vídeos médicos para aprendizagem ou pesquisa |

---

## Aviso Importante

> Este software é uma **prova de conceito em desenvolvimento**, construída para demonstrar a viabilidade de integrar em um único ambiente o player de vídeo, as ferramentas de anotação e a estrutura de gerenciamento de objetos.
>
> - Algumas funcionalidades ainda estão em expansão
> - O desempenho pode variar conforme o tamanho do vídeo e a complexidade das anotações
> - **Esta versão ainda não passou por validação clínica formal**

---

## Requisitos

### Sistema Operacional
- Windows 10/11
- Linux (Ubuntu 20.04+)
- macOS 11+

### Dependências
- Python 3.10 ou superior
- PySide6 (Qt6 para Python)

---

## Instalação

### 1. Clone o repositório

```bash
git clone https://github.com/caioseda/MLVideoEditor.git
cd MLVideoEditor
```

### 2. Crie um ambiente virtual (recomendado)

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux/macOS
python3 -m venv venv
source venv/bin/activate
```

### 3. Instale as dependências

Instale as bibliotecas do arquivo `requirements.txt`:

```bash
pip install -r requirements.txt
```

---

## Como Executar

### Opção 1: Executar o arquivo principal

```bash
python main.py
```

---

## Guia Rápido de Uso

### Carregar um Vídeo
- **Menu:** Arquivo → Abrir
- **Drag & Drop:** Arraste o arquivo de vídeo para a janela do programa
- **Formatos suportados:** AVI, MP4

### Navegação
| Ação | Controle |
|------|----------|
| Play/Pause | Botão ▶/⏸ ou `Espaço` |
| Avançar 1 frame | `→` (seta direita) |
| Retroceder 1 frame | `←` (seta esquerda) |
| Ir para posição | Clique na timeline |

### Ferramentas de Anotação
| Ferramenta | Botão | Descrição |
|------------|-------|-----------|
| Seleção | 🖱 | Cursor padrão |
| Mão (Pan) | ✋ | Mover visualização com zoom |
| Ponto | ● | Marcar pontos de interesse |
| Reta | ╱ | Desenhar linhas |
| Ângulo | ∠ | Medir ângulos (Shift = 90°) |
| Free-hand | ◌ | Desenho livre para máscaras |
| Brush | 🖌 | Pincel para máscaras |

### Configurar Ferramentas
- **Clique direito** no botão da ferramenta para acessar opções de cor, tamanho e espessura

### Exportar Máscara Binária
1. Crie uma máscara usando Free-hand ou Brush
2. Na árvore de frames, clique com **botão direito** na máscara (▣)
3. Selecione "Criar máscara binária..."
4. Escolha o local para salvar o arquivo PNG

---

## 📁 Estrutura do Projeto

```
MLVideoEditor/
├── videoml_editor/
│   ├── __init__.py
│   ├── app.py                 # Ponto de entrada da aplicação
│   ├── main_window.py         # Janela principal e lógica da UI
│   ├── video_view.py          # Visualização do vídeo e anotações
│   └── player_controller.py   # Controle de reprodução de vídeo
├── README.md
├── requirements.txt
└── main.py
└── ...
```

---

## Funcionalidades

### Implementadas
- [x] Carregamento de vídeos (AVI, MP4)
- [x] Navegação frame a frame
- [x] Controles de play/pause
- [x] Zoom e pan na visualização
- [x] Anotação de pontos
- [x] Anotação de retas
- [x] Anotação de ângulos (com suporte a 90° via Shift)
- [x] Máscara free-hand
- [x] Máscara brush
- [x] Exportação de máscaras binárias (PNG)
- [x] Organização hierárquica de frames e geometrias
- [x] Renomear/deletar anotações

### Em Desenvolvimento 
- [ ] Salvamento/carregamento de projetos
- [ ] Exportação de anotações em formato estruturado
- [ ] Suporte a mais formatos de vídeo
- [ ] Validação clínica

---

*Desenvolvido para apoiar a análise clínica e pesquisa em videofluoroscopia da deglutição.*
