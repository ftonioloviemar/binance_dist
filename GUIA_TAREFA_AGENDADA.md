# 🤖 Adaptive Crypto Bot - Guia de Configuração da Tarefa Agendada

## 📋 **Resumo da Decisão**

✅ **Recomendação: Use `adaptive_bot.py` via `run_adaptive_bot.bat`** para sua tarefa agendada diária

## 🎯 **Por que adaptive_bot.py é melhor para automação?**

### ✅ **Vantagens do adaptive_bot.py:**
- **Logs detalhados** com emojis e timestamps
- **Histórico de sentimentos** salvos automaticamente  
- **Tratamento de erros** robusto
- **Estatísticas de execução** completas
- **Mensagens claras** de sucesso/falha
- **Monitoramento** de performance

### ❌ **Desvantagens do app.py direto:**
- Logs básicos, difíceis de monitorar
- Sem histórico de execuções
- Tratamento de erros limitado
- Menos informações para debugging

---

## 🔧 **Configuração da Tarefa Agendada no Windows**

### **Opção 1: Script Simples (Recomendado)**
Use o arquivo: `run_adaptive_bot.bat`

### **Opção 2: Versão Avançada** 
Use o arquivo: `run_adaptive_bot_advanced.bat` (com monitoramento completo)

---

## 📅 **Passo a Passo para Configurar no Windows Task Scheduler**

### **1. Abrir o Agendador de Tarefas**
```
Pressione Win + R → digite "taskschd.msc" → Enter
```

### **2. Criar Nova Tarefa**
```
Clique em "Criar Tarefa Básica..." (lado direito)
```

### **3. Configurar a Tarefa**

**Nome da Tarefa:** `Adaptive Crypto Bot - Rebalanceamento Diário`

**Descrição:** `Executa rebalanceamento automático baseado em sentimento de mercado`

### **4. Configurar Gatilho (Trigger)**
```
Iniciar: Diariamente
Hora: 09:00 (ou seu horário preferido)
Repetir a cada: 1 dias
```

**💡 Recomendação:** Execute 2x ao dia em mercados voláteis:
- 09:00 (abertura mercado EUA)
- 21:00 (abertura mercado Ásia)

### **5. Configurar Ação**
```
Ação: Iniciar um programa
Programa/script: C:\python\binance_dist\run_adaptive_bot.bat

⚠️  IMPORTANTE: Use o caminho COMPLETO do arquivo .bat
```

### **6. Configurações Adicionais**

**Na aba "Condições":**
- ✅ "Iniciar somente se a conexão de rede estiver disponível"
- ✅ "Parar se o computador estiver rodando com bateria" (opcional)

**Na aba "Configurações":**
- ✅ "Permitir executar tarefa sob demanda"
- ✅ "Repetir tarefa se falhar" → Cada: 30 minutos → Tentar: 3 vezes
- ✅ "Parar a tarefa se executar por mais de: 1 hora"

---

## 🔍 **Como Monitorar suas Execuções**

### **1. Verificar Logs Diários**
```powershell
# Abrir último log
cd C:\python\binance_dist
notepad logs\adaptive_bot_$(Get-Date -Format 'yyyyMMdd').log
```

### **2. Verificar Histórico de Sentimentos**
```powershell
# Ver sentimentos anteriores
notepad sentiment_history.json
```

### **3. Verificar se a Tarefa Está Funcionando**
```
Task Scheduler → Biblioteca do Agendador de Tarefas → 
Encontrar sua tarefa → Verificar "Última execução" e "Próxima execução"
```

---

## 🚨 **Alertas e Notificações**

### **Quando Investigar:**
- ❌ Tarefa falhou 2+ vezes consecutivas
- ⚠️  Logs mostram "ERRO CRÍTICO"
- 📊 Sentimento mudou drasticamente (ex: Extreme Fear → Extreme Greed)
- 💰 Saldo não está mudando conforme esperado

### **Como Investigar Problemas:**
1. **Ver logs detalhados:** `logs\adaptive_bot_detailed_*.log`
2. **Testar manualmente:** Execute `.\run_adaptive_bot.bat` no terminal
3. **Verificar conexão:** Teste sua internet e API keys
4. **Checar espaço em disco:** Logs podem crescer com o tempo

---

## 📊 **Rotina de Manutenção Semanal**

### **Toda Segunda-feira:**
```powershell
# 1. Verificar espaço em disco
dir C:\python\binance_dist\logs | findstr "bytes"

# 2. Limpar logs antigos (manter últimos 30 dias)
forfiles /p "C:\python\binance_dist\logs" /m "*.log" /d -30 /c "cmd /c del @path"

# 3. Verificar estatísticas do histórico
python -c "from sentiment_history import get_sentiment_history; h=get_sentiment_history(); print(h.get_statistics())"
```

---

## 🎯 **Configurações Recomendadas por Tipo de Mercado**

### **Mercado em Queda (Bear Market)**
```
Frequência: 2x ao dia (09:00, 21:00)
Script: run_adaptive_bot_advanced.bat
Monitoramento: Diário
```

### **Mercado Estável (Sideways)**
```
Frequência: 1x ao dia (10:00)
Script: run_adaptive_bot.bat  
Monitoramento: 2x por semana
```

### **Mercado em Alta (Bull Market)**
```
Frequência: 1x ao dia (11:00)
Script: run_adaptive_bot.bat
Monitoramento: 1x por semana
```

---

## 🔧 **Comandos Úteis para Teste**

```bash
# Testar execução manual (simulação)
.\run_adaptive_bot.bat

# Testar execução avançada
.\run_adaptive_bot_advanced.bat

# Ver logs em tempo real
Get-Content logs\adaptive_bot_$(Get-Date -Format 'yyyyMMdd').log -Wait

# Testar apenas o bot Python
python adaptive_bot.py --dry-run
```

---

## 📞 **Suporte e Troubleshooting**

### **Problemas Comuns:**

1. **"Python não encontrado"**
   → Certifique-se de que UV está instalado e no PATH

2. **"Script não encontrado"**
   → Use caminho completo: `C:\python\binance_dist\run_adaptive_bot.bat`

3. **"Tarefa não executa"**
   → Verifique permissões (executar como administrador)
   → Confirme que o computador não está em modo de hibernação

4. **"Logs não atualizam"**
   → Verifique espaço em disco
   → Confirme permissões de escrita na pasta

---

## 🎉 **Parabéns!**

Seu **Adaptive Crypto Bot** está agora totalmente automatizado e irá:
- 🧠 **Detectar sentimento de mercado** automaticamente
- 🛡️ **Proteger seu capital** em quedas severas  
- 📈 **Aproveitar oportunidades** quando o mercado melhorar
- 📊 **Gerar logs detalhados** para monitoramento
- 🔄 **Executar 24/7** sem intervenção manual

**Próxima etapa:** Configure sua tarefa agendada e deixe o bot trabalhar para você! 🚀