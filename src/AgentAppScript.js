/**
 * ==============================================================
 * AGENTE INTELIGENTE DE GMAIL
 * ==============================================================
 * Objetivo:
 * - Classificar emails em categorias claras
 * - Sugerir prioridade e proxima acao
 * - Aprender com correcoes manuais do usuario
 * - Criar novas regras dinamicas a partir desse aprendizado
 *
 * Modo seguro:
 * - Por padrao, o script apenas sugere e aplica labels.
 * - Arquivamento automatico pode ser habilitado explicitamente.
 *
 * Melhorias aplicadas:
 * - BUG-JS-1: trigger hourly instalado em qualquer modo de execução
 * - BUG-JS-2: learnFromUserCorrections chamado apenas uma vez por execução
 * - BUG-JS-3: suggestContactAction removido do loop por thread (opção separada)
 * - BUG-JS-4: paginação ativa em modo não-histórico
 * - BUG-JS-5: getCategoryLabel com fallback explícito e log de aviso
 * - BUG-JS-6: proteção contra execução paralela de triggers
 */

const CONFIG = {
  PROCESS_ALL_HISTORY: false,
  TIME_FILTER: "newer_than:2d",
  BATCH_SIZE: 100,
  MAX_REPORT_THREADS: 50,
  MAX_EXECUTION_TIME_MS: 4.5 * 60 * 1000,
  ENABLE_AUTO_ARCHIVE: false,
  ENABLE_MARK_IMPORTANT: true,
  LEARNING_WINDOW_QUERY: "has:userlabels newer_than:14d",
  CONTACT_SUGGESTION_MIN_COUNT: 3,
  MIN_KEYWORD_LENGTH: 4,
  MAX_KEYWORDS_PER_RULE: 6
};

const LABELS = {
  ROOT: "AGENTE",
  URGENTE: "AGENTE/URGENTE",
  TRABALHO: "AGENTE/TRABALHO",
  PESSOAL: "AGENTE/PESSOAL",
  PROMOCOES: "AGENTE/PROMOCOES",
  NOTIFICACOES: "AGENTE/NOTIFICACOES",
  REVISAO: "AGENTE/REVISAR",
  APRENDIDO: "AGENTE/APRENDIDO",
  CONTATOS: "AGENTE/CONTATOS",
  FINANCEIRO: "AGENTE/FINANCEIRO"  // BUG-JS-5: categoria em falta no mapa original
};

const STATIC_RULES = [
  { category: "URGENTE", query: "from:(mail.notion.so OR silvia.calado@medialcare.pt) OR subject:(urgente OR urgent)" },
  { category: "PROMOCOES", query: "from:(news@mkt.americanas.com OR info@ourbusinessnetwork.com OR newsletter@deals.banggood.com)" },
  { category: "PROMOCOES", query: "from:(alert@indeed.com) OR list:(<75088.1.jradmin.jobrapidoalert.com>)" },
  { category: "NOTIFICACOES", query: "from:(noreply@redditmail.com OR linkedin.com OR lc@opendns.com)" },
  { category: "TRABALHO", query: "from:(alerts@englishclass101.com OR quincy@freecodecamp.org OR lira@hashtagtreinamentos.com OR contato@devsuperior.com OR mail@doutoresdoexcel.eadplataforma.com OR doutores@doutoresdoexcel.com.br OR alert@notify.coursary.com)" },
  { category: "PESSOAL", query: "from:(amazon.es OR amazon.com OR amazon.com.br OR cartaounibanco@unicre.pt OR extratos@unicre.pt OR nao-responder@enotas.com.br OR mercadopago.com OR picpay.com OR vivo.com.br OR claro.com.br OR tim.com.br OR oi.com.br OR ComunicacoesCartao@clientesfnacpt.caixabankpc.com OR noreply@cartaocontinente.pt OR mun.montijo.pt@cgi.com)" }
];

const PRIORITY_RULES = {
  high: [
    "urgente", "urgent", "prazo", "deadline", "hoje", "today",
    "suporte", "support", "erro", "problema", "problem",
    "falha", "failure", "acao necessaria", "action required",
    "responda", "reply needed", "asap", "imediato"
  ],
  medium: [
    "fatura", "boleto", "pagamento", "pedido", "comprovante",
    "reuniao", "meeting", "agenda", "notificacao", "notification"
  ]
};

// ---------------------------------------------------------------------------
// BUG-JS-6: Lock de execução para evitar runs paralelos
// ---------------------------------------------------------------------------
function isAlreadyRunning() {
  const properties = PropertiesService.getScriptProperties();
  const lock = properties.getProperty("EXECUTION_LOCK");
  if (!lock) return false;
  const lockTime = parseInt(lock, 10);
  // Se o lock tiver mais de 10 minutos, considerar obsoleto
  return (Date.now() - lockTime) < 10 * 60 * 1000;
}

function acquireLock() {
  PropertiesService.getScriptProperties().setProperty("EXECUTION_LOCK", String(Date.now()));
}

function releaseLock() {
  PropertiesService.getScriptProperties().deleteProperty("EXECUTION_LOCK");
}

// ---------------------------------------------------------------------------
// Setup inicial
// ---------------------------------------------------------------------------
function runFirstTimeSetup() {
  removeTriggersByName("executePlan");
  removeTriggersByName("resumeExecution");
  PropertiesService.getScriptProperties().deleteAllProperties();
  CONFIG.PROCESS_ALL_HISTORY = true;
  executePlan();
}

// ---------------------------------------------------------------------------
// Plano principal de execução
// BUG-JS-2: learnFromUserCorrections chamado apenas aqui, uma vez por run
// BUG-JS-1: installTrigger chamado sempre no final, não só em modo histórico
// BUG-JS-6: proteção contra execução paralela
// ---------------------------------------------------------------------------
function executePlan() {
  // BUG-JS-6: verificar lock
  if (isAlreadyRunning()) {
    Logger.log("[executePlan] Outra execucao em curso. Abortando para evitar paralelismo.");
    return;
  }

  acquireLock();
  const startTime = Date.now();

  try {
    const properties = PropertiesService.getScriptProperties();

    // BUG-JS-2: aprendizado chamado uma única vez, aqui no início
    learnFromUserCorrections();

    let currentStepIndex = 0;
    let currentOffset = 0;

    if (CONFIG.PROCESS_ALL_HISTORY) {
      currentStepIndex = parseInt(properties.getProperty("SAVED_STEP_INDEX") || "0", 10);
      currentOffset = parseInt(properties.getProperty("SAVED_OFFSET") || "0", 10);
      properties.deleteProperty("SAVED_STEP_INDEX");
      properties.deleteProperty("SAVED_OFFSET");
    }

    const fullPlan = buildFullPlan();

    for (let i = currentStepIndex; i < fullPlan.length; i++) {
      const step = fullPlan[i];
      const query = CONFIG.PROCESS_ALL_HISTORY
        ? step.query
        : `(${step.query}) ${CONFIG.TIME_FILTER}`;
      const finished = processRule(query, step.category, currentOffset, i, startTime);
      if (!finished && CONFIG.PROCESS_ALL_HISTORY) {
        // Estado guardado dentro de processRule → saveStateAndScheduleResume
        return;
      }
      currentOffset = 0;
    }

    // BUG-JS-1: instalar trigger em qualquer modo, não só no histórico
    installTrigger();
    Logger.log("[executePlan] Concluido. Trigger hourly instalado.");

  } finally {
    releaseLock();
  }
}

// ---------------------------------------------------------------------------
// Processamento de regras e threads
// BUG-JS-4: paginação ativa também em modo não-histórico
// ---------------------------------------------------------------------------
function processRule(query, category, initialOffset, stepIndex, startTime) {
  const label = getOrCreateLabel(getCategoryLabel(category));
  let start = initialOffset;
  let threads = [];

  do {
    // Verificar tempo restante
    if (Date.now() - startTime >= CONFIG.MAX_EXECUTION_TIME_MS) {
      if (CONFIG.PROCESS_ALL_HISTORY) {
        saveStateAndScheduleResume(stepIndex, start);
        return false;
      }
      // Em modo normal: parar sem salvar estado (próximo run pega do zero)
      Logger.log("[processRule] Tempo limite atingido em modo normal. Parando.");
      return true;
    }

    threads = GmailApp.search(query, start, CONFIG.BATCH_SIZE);
    if (threads.length > 0) {
      classifyThreads(threads, label, category);
    }
    start += CONFIG.BATCH_SIZE;

    // BUG-JS-4: paginar em AMBOS os modos enquanto houver threads
  } while (threads.length === CONFIG.BATCH_SIZE);

  return true;
}

// ---------------------------------------------------------------------------
// Classificação de threads
// BUG-JS-3: suggestContactAction removido do loop — evita N búscas por thread
// ---------------------------------------------------------------------------
function classifyThreads(threads, label, forcedCategory) {
  const reviewLabel = getOrCreateLabel(LABELS.REVISAO);
  label.addToThreads(threads);

  threads.forEach(thread => {
    const analysis = analyzeThread(thread, forcedCategory);

    if (analysis.priority === "alta" && CONFIG.ENABLE_MARK_IMPORTANT) {
      GmailApp.markThreadImportant(thread);
    }

    if (analysis.action === "arquivar" && CONFIG.ENABLE_AUTO_ARCHIVE) {
      thread.moveToArchive();
    }

    if (analysis.priority === "alta" || analysis.category === "URGENTE") {
      reviewLabel.addToThread(thread);
    }
  });
}

// ---------------------------------------------------------------------------
// Análise de inbox (para uso manual/relatórios)
// BUG-JS-2: learnFromUserCorrections NÃO é chamado aqui — evita duplicação
// ---------------------------------------------------------------------------
function analyzeInbox() {
  const query = CONFIG.PROCESS_ALL_HISTORY ? "in:anywhere" : `in:anywhere ${CONFIG.TIME_FILTER}`;
  const threads = GmailApp.search(query, 0, CONFIG.MAX_REPORT_THREADS);
  const report = threads.map(thread => analyzeThread(thread));
  Logger.log(JSON.stringify(report, null, 2));
  return report;
}

function analyzeThread(thread, forcedCategory) {
  const firstMessage = thread.getMessages()[0];
  const subject = (firstMessage.getSubject() || "").trim();
  const from = normalizeEmailAddress(firstMessage.getFrom());
  const domain = extractDomain(from);
  const snippet = sanitizeSnippet(thread.getFirstMessageSubject(), firstMessage.getPlainBody());
  const learnedCategory = getLearnedCategoryForThread(from, domain, subject, snippet);
  const category = forcedCategory || learnedCategory || inferCategory(from, subject, snippet);
  const priority = inferPriority(category, subject, snippet);
  const summary = buildSummary(subject, snippet, priority);
  const action = suggestAction(category, priority);
  const reply = suggestReply(category, priority, subject);
  // BUG-JS-3: contactSuggestion removido do loop — usar suggestContactActionBatch separadamente

  return {
    sender: from,
    subject: subject,
    category: category,
    priority: priority,
    summary: summary,
    action: action,
    reply: reply
  };
}

// ---------------------------------------------------------------------------
// Sugestão de contatos — agora como função separada para uso fora do loop
// BUG-JS-3: não mais chamada dentro de analyzeThread()
// ---------------------------------------------------------------------------
function suggestContactActionBatch(report) {
  return report.map(item => {
    const count = GmailApp.search(`from:${item.sender}`, 0, CONFIG.CONTACT_SUGGESTION_MIN_COUNT).length;
    return {
      sender: item.sender,
      contactSuggestion: count >= CONFIG.CONTACT_SUGGESTION_MIN_COUNT
        ? `Sugerir contato/grupo: ${item.category.toLowerCase()}`
        : ""
    };
  });
}

// ---------------------------------------------------------------------------
// Aprendizado com correções manuais do utilizador
// ---------------------------------------------------------------------------
function learnFromUserCorrections() {
  const properties = PropertiesService.getScriptProperties();
  const rules = JSON.parse(properties.getProperty("LEARNED_RULES") || '{"bySender":{},"byDomain":{},"byKeyword":{},"bySubject":{}}');
  const threads = GmailApp.search(CONFIG.LEARNING_WINDOW_QUERY, 0, CONFIG.MAX_REPORT_THREADS);
  let changed = false;

  threads.forEach(thread => {
    const labels = thread.getLabels().map(label => label.getName());
    const categoryLabel = labels.find(name => name.indexOf(LABELS.ROOT + "/") === 0);
    if (!categoryLabel) {
      return;
    }

    const sender = normalizeEmailAddress(thread.getMessages()[0].getFrom());
    const domain = extractDomain(sender);
    const subject = (thread.getMessages()[0].getSubject() || "").trim();
    const body = thread.getMessages()[0].getPlainBody() || "";
    const category = categoryLabel.split("/").pop();
    const keywords = extractKeywords(`${subject} ${body}`);

    changed = learnSenderRule(rules, sender, category) || changed;
    changed = learnDomainRule(rules, domain, category) || changed;
    changed = learnSubjectRule(rules, subject, category) || changed;

    keywords.forEach(keyword => {
      changed = learnKeywordRule(rules, keyword, category) || changed;
    });
  });

  if (changed) {
    properties.setProperty("LEARNED_RULES", JSON.stringify(rules));
  }
}

function buildFullPlan() {
  const properties = PropertiesService.getScriptProperties();
  const rules = JSON.parse(properties.getProperty("LEARNED_RULES") || '{"bySender":{},"byDomain":{},"byKeyword":{},"bySubject":{}}');
  const dynamicRules = [];
  const senderGroups = groupLearnedEntries(rules.bySender || {});
  const domainGroups = groupLearnedEntries(rules.byDomain || {});
  const keywordGroups = groupLearnedEntries(rules.byKeyword || {}, 2);
  const subjectGroups = groupLearnedEntries(rules.bySubject || {}, 2);

  Object.keys(senderGroups).forEach(category => {
    dynamicRules.push({
      category: category,
      query: `from:(${senderGroups[category].join(" OR ")})`
    });
  });

  Object.keys(domainGroups).forEach(category => {
    dynamicRules.push({
      category: category,
      query: domainGroups[category].map(domain => `from:(@${domain})`).join(" OR ")
    });
  });

  Object.keys(keywordGroups).forEach(category => {
    dynamicRules.push({
      category: category,
      query: keywordGroups[category].map(keyword => `"${keyword}"`).join(" OR ")
    });
  });

  Object.keys(subjectGroups).forEach(category => {
    dynamicRules.push({
      category: category,
      query: subjectGroups[category].map(subject => `subject:("${subject}")`).join(" OR ")
    });
  });

  return dynamicRules.concat(STATIC_RULES);
}

function getLearnedCategoryForThread(sender, domain, subject, snippet) {
  const rules = JSON.parse(PropertiesService.getScriptProperties().getProperty("LEARNED_RULES") || '{"bySender":{},"byDomain":{},"byKeyword":{},"bySubject":{}}');
  if (rules.bySender && rules.bySender[sender]) {
    return rules.bySender[sender].category;
  }
  if (rules.bySubject && rules.bySubject[normalizeSubject(subject)]) {
    return rules.bySubject[normalizeSubject(subject)].category;
  }
  if (rules.byDomain && rules.byDomain[domain] && rules.byDomain[domain].confidence >= 2) {
    return rules.byDomain[domain].category;
  }

  const keywordMatch = matchLearnedKeyword(rules.byKeyword || {}, `${subject} ${snippet}`);
  return keywordMatch ? keywordMatch.category : null;
}

function inferCategory(sender, subject, snippet) {
  const haystack = `${sender} ${subject} ${snippet}`.toLowerCase();

  if (hasAnyKeyword(haystack, PRIORITY_RULES.high)) {
    return "URGENTE";
  }
  if (/(invoice|fatura|boleto|pagamento|support|cliente|projeto|meeting|reuniao|contrato)/i.test(haystack)) {
    return "TRABALHO";
  }
  if (/(promo|newsletter|sale|deal|cupom|oferta|desconto)/i.test(haystack)) {
    return "PROMOCOES";
  }
  if (/(notification|notificacao|alerta|reddit|linkedin|system|sistema)/i.test(haystack)) {
    return "NOTIFICACOES";
  }
  return "PESSOAL";
}

function inferPriority(category, subject, snippet) {
  const haystack = `${subject} ${snippet}`.toLowerCase();
  if (category === "URGENTE" || hasAnyKeyword(haystack, PRIORITY_RULES.high)) {
    return "alta";
  }
  if (category === "TRABALHO" || hasAnyKeyword(haystack, PRIORITY_RULES.medium)) {
    return "media";
  }
  return "baixa";
}

function buildSummary(subject, snippet, priority) {
  const objective = subject || "Email sem assunto";
  const action = priority === "alta" ? "Exige revisao rapida." : "Sem acao imediata aparente.";
  const shortSnippet = snippet ? snippet.substring(0, 140) : "Sem contexto adicional.";
  return `${objective}. ${action} ${shortSnippet}`;
}

function suggestAction(category, priority) {
  if (category === "URGENTE" || priority === "alta") {
    return "manter na caixa, aplicar label e revisar";
  }
  if (category === "PROMOCOES" || category === "NOTIFICACOES") {
    return "aplicar label e sugerir arquivamento";
  }
  return "aplicar label e organizar";
}

function suggestReply(category, priority, subject) {
  if (category === "URGENTE" || priority === "alta") {
    return `Recebi sua mensagem sobre "${subject}". Vou analisar e retornar o quanto antes.`;
  }
  if (category === "TRABALHO") {
    return `Recebi seu email. Vou revisar os detalhes e responder com os proximos passos.`;
  }
  return "";
}

// ---------------------------------------------------------------------------
// Gestão de triggers
// BUG-JS-1 corrigido: installTrigger() sempre garante exactamente 1 trigger hourly
// ---------------------------------------------------------------------------
function installTrigger() {
  removeTriggersByName("executePlan");
  ScriptApp.newTrigger("executePlan").timeBased().everyHours(1).create();
  Logger.log("[installTrigger] Trigger hourly para executePlan instalado.");
}

function resumeExecution() {
  removeTriggersByName("resumeExecution");
  CONFIG.PROCESS_ALL_HISTORY = true;
  executePlan();
}

function saveStateAndScheduleResume(stepIndex, currentOffset) {
  const properties = PropertiesService.getScriptProperties();
  properties.setProperty("SAVED_STEP_INDEX", String(stepIndex));
  properties.setProperty("SAVED_OFFSET", String(currentOffset));
  removeTriggersByName("resumeExecution");
  ScriptApp.newTrigger("resumeExecution").timeBased().after(1 * 60 * 1000).create();
  Logger.log(`[saveStateAndScheduleResume] Estado salvo: step=${stepIndex}, offset=${currentOffset}. Resume agendado em 1 min.`);
}

function removeTriggersByName(functionName) {
  ScriptApp.getProjectTriggers().forEach(trigger => {
    if (trigger.getHandlerFunction() === functionName) {
      ScriptApp.deleteTrigger(trigger);
    }
  });
}

// ---------------------------------------------------------------------------
// Utilitários de labels
// BUG-JS-5 corrigido: fallback explícito com log de aviso em vez de silencioso
// ---------------------------------------------------------------------------
function getCategoryLabel(category) {
  const label = LABELS[category];
  if (label) {
    return label;
  }
  Logger.log(`[getCategoryLabel] AVISO: categoria desconhecida "${category}" — usando REVISAO como fallback seguro.`);
  return LABELS.REVISAO;  // REVISAO é mais seguro que PESSOAL como fallback
}

function getOrCreateLabel(name) {
  return GmailApp.getUserLabelByName(name) || GmailApp.createLabel(name);
}

function normalizeEmailAddress(fromValue) {
  const match = (fromValue || "").match(/<([^>]+)>/);
  return (match ? match[1] : fromValue || "").trim().toLowerCase();
}

function extractDomain(email) {
  const parts = (email || "").split("@");
  return parts.length > 1 ? parts[1].trim().toLowerCase() : "";
}

function normalizeSubject(subject) {
  return (subject || "").toLowerCase().replace(/\s+/g, " ").trim();
}

function sanitizeSnippet(subject, body) {
  const merged = `${subject || ""} ${body || ""}`
    .replace(/\s+/g, " ")
    .replace(/[<>]/g, "")
    .trim();
  return merged.substring(0, 220);
}

function hasAnyKeyword(text, keywords) {
  return keywords.some(keyword => text.indexOf(keyword) >= 0);
}

function extractKeywords(text) {
  const stopWords = {
    de: true, da: true, do: true, das: true, dos: true, para: true, por: true, com: true,
    que: true, seu: true, sua: true, this: true, that: true, from: true, you: true,
    about: true, and: true, the: true, uma: true, um: true, em: true, no: true, na: true
  };

  const tokens = (text || "")
    .toLowerCase()
    .replace(/[^a-z0-9\u00C0-\u017F\s]/g, " ")
    .split(/\s+/)
    .filter(token => token.length >= CONFIG.MIN_KEYWORD_LENGTH && !stopWords[token]);

  const unique = [];
  tokens.forEach(token => {
    if (unique.indexOf(token) === -1) {
      unique.push(token);
    }
  });

  return unique.slice(0, CONFIG.MAX_KEYWORDS_PER_RULE);
}

function learnSenderRule(rules, sender, category) {
  return upsertLearnedRule(rules.bySender, sender, category);
}

function learnDomainRule(rules, domain, category) {
  if (!domain) {
    return false;
  }
  return upsertLearnedRule(rules.byDomain, domain, category, true);
}

function learnSubjectRule(rules, subject, category) {
  const normalized = normalizeSubject(subject);
  if (!normalized || normalized.length < 6) {
    return false;
  }
  return upsertLearnedRule(rules.bySubject, normalized, category, true);
}

function learnKeywordRule(rules, keyword, category) {
  if (!keyword) {
    return false;
  }
  return upsertLearnedRule(rules.byKeyword, keyword, category, true);
}

function upsertLearnedRule(bucket, key, category, accumulate) {
  if (!bucket[key]) {
    bucket[key] = {
      category: category,
      source: "manual_correction",
      confidence: 1,
      updatedAt: new Date().toISOString()
    };
    return true;
  }

  if (bucket[key].category !== category) {
    bucket[key].category = category;
    bucket[key].confidence = 1;
    bucket[key].updatedAt = new Date().toISOString();
    return true;
  }

  if (accumulate) {
    bucket[key].confidence = (bucket[key].confidence || 1) + 1;
    bucket[key].updatedAt = new Date().toISOString();
    return true;
  }

  return false;
}

function groupLearnedEntries(bucket, minConfidence) {
  const grouped = {};
  Object.keys(bucket).forEach(key => {
    const entry = bucket[key];
    const confidence = entry.confidence || 1;
    if (minConfidence && confidence < minConfidence) {
      return;
    }
    if (!grouped[entry.category]) {
      grouped[entry.category] = [];
    }
    grouped[entry.category].push(key);
  });
  return grouped;
}

function matchLearnedKeyword(keywordRules, text) {
  const haystack = (text || "").toLowerCase();
  let bestMatch = null;

  Object.keys(keywordRules).forEach(keyword => {
    const entry = keywordRules[keyword];
    if ((entry.confidence || 1) < 2) {
      return;
    }
    if (haystack.indexOf(keyword) >= 0) {
      if (!bestMatch || (entry.confidence || 1) > (bestMatch.confidence || 1)) {
        bestMatch = entry;
      }
    }
  });

  return bestMatch;
}
