/**
 * Widget de assistente RAG - Disruptive Architectures
 *
 * Como usar:
 * 1. Suba este arquivo em material/js/chat-widget.js.
 * 2. No mkdocs.yml, adicione o caminho em extra_javascript, junto dos outros:
 *
 *    extra_javascript:
 *      - https://cdnjs.cloudflare.com/ajax/libs/js-yaml/4.0.0/js-yaml.min.js
 *      - https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js
 *      - js/chat-widget.js
 *
 * 3. Antes de carregar este arquivo, configure em chat-config.js:
 *      window.DA_RAG_API_URL = "https://sua-api-publicada/ask";
 *    A URL pode ser absoluta ou uma rota relativa no mesmo domínio.
 *
 * A conversa fica no sessionStorage e sobrevive à navegação entre páginas
 * durante a sessão atual da aba.
 */

(function () {
  const STORAGE_KEY = "da-rag-chat-session-v1";
  const POSITION_KEY = "da-rag-widget-position-v1";
  const MAX_HISTORY_MESSAGES = 16; // 8 trocas: o mesmo limite configurado no backend
  const SITE_HOST = "kelsonzh0.github.io";
  const SITE_PATH = "/DisruptiveArchitectures/";
  const MENSAGEM_BOAS_VINDAS =
    "Oi! Pergunte qualquer coisa sobre o conteúdo do curso (aulas, labs, conceitos).";

  // Estado que sobrevive à recriação do DOM entre navegações
  const estado = {
    aberto: false,
    mensagens: [], // { texto, who: 'user'|'bot', fontes? }
    enviando: false,
    conversaId: null,
    conversaToken: null,
    perguntaPendente: null,
    mensagemUsuarioPendente: null,
  };
  const posicoes = lerPosicoes();

  function lerPosicoes() {
    try {
      const salvo = JSON.parse(localStorage.getItem(POSITION_KEY) || "null");
      return salvo && typeof salvo === "object" ? salvo : {};
    } catch (_) {
      return {};
    }
  }

  function salvarPosicoes() {
    try {
      localStorage.setItem(POSITION_KEY, JSON.stringify(posicoes));
    } catch (_) {
      // A posição customizada é opcional se o armazenamento estiver bloqueado.
    }
  }

  function limitar(valor, minimo, maximo) {
    return Math.min(Math.max(valor, minimo), Math.max(minimo, maximo));
  }

  function obterUrlApi() {
    const configurada = typeof window.DA_RAG_API_URL === "string"
      ? window.DA_RAG_API_URL.trim()
      : "";
    if (!configurada) {
      throw new Error("A API do chat ainda não foi configurada. Defina a URL terminada em /ask no arquivo material/js/chat-config.js.");
    }
    let url;
    try {
      url = new URL(configurada, window.location.href);
    } catch (_) {
      throw new Error("A URL da API do chat é inválida. Use um endereço HTTP ou HTTPS terminado em /ask.");
    }
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password) {
      throw new Error("A URL da API do chat precisa usar HTTP ou HTTPS e não pode conter credenciais.");
    }
    return url.href;
  }

  function salvarEstado() {
    try {
      const mensagens = estado.mensagens.filter((m) => !m.loading).slice(-80).map((m) => ({
        id: m.id,
        texto: String(m.texto).slice(0, 20000),
        who: m.who,
        fontes: validarFontes(m.fontes),
        boasVindas: !!m.boasVindas,
        retryQuestion: typeof m.retryQuestion === "string" ? m.retryQuestion.slice(0, 4000) : null,
        retryUserMessageId: Number.isInteger(m.retryUserMessageId) ? m.retryUserMessageId : null,
      }));
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify({
        aberto: estado.aberto,
        mensagens,
        conversaId: estado.conversaId,
        conversaToken: estado.conversaToken,
        perguntaPendente: estado.perguntaPendente,
        mensagemUsuarioPendente: estado.mensagemUsuarioPendente,
      }));
    } catch (_) {
      // O chat continua funcionando mesmo se o navegador bloquear o storage.
    }
  }

  function obterSugestoesDaPagina() {
    const conteudo = document.querySelector(".md-content");
    const titulo = conteudo && conteudo.querySelector("h1")
      ? conteudo.querySelector("h1").textContent.trim()
      : document.title.replace(/\s+-\s+Disruptive Architectures$/, "").trim();
    const topicos = conteudo
      ? Array.from(conteudo.querySelectorAll("h2"))
        .map((heading) => heading.textContent.trim())
        .filter((heading) => !/objetivos|visão geral|entrega/i.test(heading))
      : [];
    const topico = topicos[0];
    return [
      `Quais são os objetivos de “${titulo.slice(0, 72)}”?`,
      topico ? `Explique “${topico.slice(0, 72)}” com um exemplo.` : "Resuma as ideias principais desta página.",
      "Que atividades ou entregas este material descreve?",
    ];
  }

  function mostrarSugestoes(container) {
    if (!container || container.querySelector(".da-rag-suggestions")) return;
    const jaPerguntou = estado.mensagens.some((m) => m.who === "user");
    if (jaPerguntou) return;

    const grupo = document.createElement("div");
    grupo.className = "da-rag-suggestions";
    grupo.setAttribute("role", "group");
    grupo.setAttribute("aria-label", "Sugestões de perguntas sobre esta página");
    obterSugestoesDaPagina().forEach((pergunta) => {
      const botao = document.createElement("button");
      botao.type = "button";
      botao.className = "da-rag-suggestion";
      botao.textContent = pergunta;
      grupo.appendChild(botao);
    });
    container.appendChild(grupo);
  }

  function montarWidget() {
    // Se já existe (ex: script rodou 2x na mesma página), não duplica
    if (document.getElementById("da-rag-widget")) return;

    if (!document.getElementById("da-rag-style")) {
      const style = document.createElement("style");
      style.id = "da-rag-style";
      style.textContent = `
        #da-rag-bubble {
          position: fixed; bottom: 20px; right: 20px; z-index: 9999;
          box-sizing: border-box; width: 224px; min-width: 48px; height: 52px;
          padding: 0 16px; border: none; border-radius: 999px;
          background: var(--da-rag-trigger-bg, var(--md-primary-fg-color, #3349B4));
          color: var(--da-rag-trigger-fg, var(--md-primary-bg-color, #fff));
          cursor: pointer; box-shadow: 0 3px 12px rgba(20, 24, 48, .24);
          display: flex; align-items: center; justify-content: center; gap: 9px;
          --da-rag-drag-x: 0px; --da-rag-drag-y: 0px;
          transform: translate3d(var(--da-rag-drag-x), var(--da-rag-drag-y), 0);
          transition: width 180ms cubic-bezier(.23, 1, .32, 1), padding 180ms cubic-bezier(.23, 1, .32, 1), box-shadow 180ms ease;
          touch-action: none; user-select: none; -webkit-user-select: none;
        }
        [data-md-color-scheme="default"] #da-rag-bubble { --da-rag-trigger-bg: #3349B4; --da-rag-trigger-fg: #fff; }
        [data-md-color-scheme="slate"] #da-rag-bubble { --da-rag-trigger-bg: #A6B6FF; --da-rag-trigger-fg: #1A2030; }
        #da-rag-bubble:hover { box-shadow: 0 5px 16px rgba(20, 24, 48, .3); }
        #da-rag-bubble:active:not(.is-dragging) { transform: translate3d(var(--da-rag-drag-x), var(--da-rag-drag-y), 0) scale(.97); }
        #da-rag-bubble.is-dragging { cursor: grabbing; transition: none; }
        #da-rag-bubble.is-snapping { transition: transform 220ms cubic-bezier(.23, 1, .32, 1); }
        #da-rag-bubble.is-compact { width: 52px; padding-right: 0; padding-left: 0; }
        #da-rag-bubble .da-rag-trigger-icon {
          position: absolute; left: 16px; top: 50%; margin-top: -12px;
          display: block; width: 24px; height: 24px;
          transition: left 180ms cubic-bezier(.23, 1, .32, 1), opacity 150ms ease-out, transform 180ms cubic-bezier(.23, 1, .32, 1);
        }
        #da-rag-bubble.is-compact .da-rag-trigger-icon { left: calc(50% - 12px); }
        #da-rag-bubble .da-rag-trigger-chat { opacity: 1; transform: rotate(0) scale(1); }
        #da-rag-bubble .da-rag-trigger-close { opacity: 0; transform: rotate(-45deg) scale(.82); }
        #da-rag-bubble.is-open .da-rag-trigger-chat { opacity: 0; transform: rotate(45deg) scale(.82); }
        #da-rag-bubble.is-open .da-rag-trigger-close { opacity: 1; transform: rotate(0) scale(1); }
        #da-rag-bubble .da-rag-trigger-label {
          display: inline-block; margin-left: 32px; overflow: hidden; white-space: nowrap;
          font: 600 13px/1 var(--md-text-font-family, sans-serif);
          opacity: 1; transform: translateX(0);
          transition: opacity 120ms ease, transform 180ms cubic-bezier(.23, 1, .32, 1), max-width 180ms ease;
          max-width: 160px;
        }
        #da-rag-bubble.is-compact .da-rag-trigger-label { max-width: 0; opacity: 0; transform: translateX(5px); }
        #da-rag-bubble:focus-visible, #da-rag-close:focus-visible,
        #da-rag-new:focus-visible, #da-rag-menu > summary:focus-visible,
        #da-rag-send:focus-visible, .da-rag-suggestion:focus-visible,
        .da-rag-retry:focus-visible {
          outline: 2px solid var(--da-rag-focus-color, #3349B4);
          outline-offset: 2px;
        }
        #da-rag-widget {
          position: fixed; bottom: 88px; right: 24px; z-index: 9999;
          box-sizing: border-box; width: 380px; max-width: calc(100vw - 48px);
          height: 560px; max-height: calc(100dvh - 120px);
          background: var(--md-default-bg-color, #fff);
          color: var(--md-default-fg-color, #000);
          border-radius: 16px; box-shadow: 0 12px 36px rgba(18, 24, 45, .24);
          display: none; flex-direction: column; overflow: hidden;
          opacity: 0; transform: scale(.95); transform-origin: bottom right;
          visibility: hidden; pointer-events: none;
          font-family: "Segoe UI", Arial, sans-serif;
          line-height: 1.5;
          border: 1px solid var(--md-default-fg-color--lightest, rgba(127,127,127,.22));
        }
        #da-rag-widget, #da-rag-widget * { box-sizing: border-box; }
        [data-md-color-scheme="default"] #da-rag-widget {
          --da-rag-focus-color: #4338A8;
          --da-rag-input-border: #d8d6e2;
          --da-rag-header-bg: #f0eff7;
          --da-rag-header-fg: #242238;
          --da-rag-header-border: #dedce8;
          --da-rag-scroll-thumb: #c2bfd0;
        }
        [data-md-color-scheme="slate"] #da-rag-widget {
          --da-rag-focus-color: #A6B6FF;
          --da-rag-input-border: #34405A;
          --da-rag-header-bg: #232B3E;
          --da-rag-header-fg: #E6EBF5;
          --da-rag-header-border: #34405A;
          --da-rag-scroll-thumb: #52617e;
        }
        #da-rag-widget button, #da-rag-widget input { font-family: inherit; }
        #da-rag-widget.open { display: flex; opacity: 1; transform: scale(1); visibility: visible; pointer-events: auto; }
        #da-rag-widget.closing { display: flex; visibility: visible; pointer-events: none; }
        #da-rag-header {
          position: relative; z-index: 1; flex: 0 0 auto;
          background: var(--da-rag-header-bg, #f0eff7); color: var(--da-rag-header-fg, #242238);
          border-bottom: 1px solid var(--da-rag-header-border, #dedce8);
          padding: 10px 12px 10px 16px; font-weight: 600; font-size: 14px;
          display: flex; justify-content: space-between; align-items: center;
          cursor: grab; touch-action: none; user-select: none; -webkit-user-select: none;
        }
        #da-rag-header.is-dragging { cursor: grabbing; }
        #da-rag-header-actions { display: flex; align-items: center; gap: 4px; }
        #da-rag-header-actions > button, #da-rag-menu > summary {
          box-sizing: border-box; width: 36px; height: 36px; padding: 0;
          display: grid; place-items: center; border: 0; border-radius: 10px;
          background: transparent; color: inherit; cursor: pointer; touch-action: auto;
          transition: background-color 150ms ease, transform 120ms ease-out;
        }
        #da-rag-header-actions > button:hover, #da-rag-menu > summary:hover {
          background: color-mix(in srgb, currentColor 10%, transparent);
        }
        #da-rag-header-actions > button:active, #da-rag-menu > summary:active { transform: scale(.96); }
        #da-rag-header-actions svg { width: 18px; height: 18px; display: block; }
        #da-rag-menu { position: relative; }
        #da-rag-menu > summary { list-style: none; }
        #da-rag-menu > summary::-webkit-details-marker { display: none; }
        #da-rag-menu-content { position: absolute; z-index: 2; right: 0; top: calc(100% + 7px); width: max-content; max-width: calc(100vw - 32px); padding: 5px; border-radius: 8px; background: var(--md-default-bg-color, #fff); color: var(--md-default-fg-color, #000); box-shadow: 0 5px 18px rgba(0,0,0,.24); border: 1px solid var(--md-default-fg-color--lightest, rgba(127,127,127,.22)); }
        #da-rag-reset-position { border: 0; border-radius: 5px; padding: 8px 10px; background: transparent; color: inherit; font: inherit; font-size: 12px; white-space: nowrap; }
        #da-rag-reset-position:hover { background: var(--md-default-bg-color--light, var(--md-code-bg-color, #f0f0f0)); }
        #da-rag-messages {
          box-sizing: border-box; flex: 1; min-width: 0; overflow-y: auto;
          padding: 14px 16px; font-size: 13.5px; line-height: 1.5;
          scrollbar-width: thin; scrollbar-color: var(--da-rag-scroll-thumb, #c2bfd0) transparent;
        }
        #da-rag-messages::-webkit-scrollbar { width: 6px; }
        #da-rag-messages::-webkit-scrollbar-track { background: transparent; }
        #da-rag-messages::-webkit-scrollbar-thumb { border-radius: 999px; background: var(--da-rag-scroll-thumb, #c2bfd0); }
        .da-rag-msg { margin-bottom: 12px; }
        .da-rag-msg.user { display: flex; justify-content: flex-end; }
        .da-rag-msg .bubble {
          display: block; box-sizing: border-box; width: fit-content; max-width: 85%;
          padding: 8px 12px; border-radius: 12px; text-align: left;
          white-space: pre-wrap; overflow-wrap: anywhere;
        }
        .da-rag-msg.user .bubble { background: var(--md-primary-fg-color, #3730a3); color: var(--md-primary-bg-color, #fff); }
        .da-rag-msg.bot .bubble {
          width: 100%; max-width: 100%; padding: 0; border: 0; border-radius: 0;
          background: transparent; color: inherit;
        }
        .da-rag-retry {
          display: inline-flex; margin: 8px 0 0; padding: 5px 9px; border-radius: 6px;
          border: 1px solid var(--md-accent-fg-color, #b9382b);
          background: transparent; color: var(--md-accent-fg-color, #b9382b);
          font: inherit; font-size: 12px; cursor: pointer;
        }
        .da-rag-retry:hover:not(:disabled) {
          background: var(--md-accent-fg-color, #b9382b);
          color: var(--md-accent-bg-color, #fff);
        }
        .da-rag-retry:focus-visible { outline: 3px solid var(--md-accent-fg-color, #b9382b); outline-offset: 2px; }
        .da-rag-retry:disabled { cursor: wait; opacity: .55; }
        .da-rag-msg .bubble p { margin: 0 0 6px 0; }
        .da-rag-msg .bubble p:last-child { margin-bottom: 0; }
        .da-rag-msg .bubble ul { margin: 4px 0; padding-left: 18px; }
        .da-rag-msg .bubble code {
          background: rgba(0,0,0,0.08); padding: 1px 4px; border-radius: 4px;
          font-size: 12px;
        }
        .da-rag-msg .bubble pre {
          background: rgba(0,0,0,0.08); padding: 8px 10px; border-radius: 6px;
          overflow-x: auto; margin: 6px 0; max-width: 100%;
        }
        .da-rag-msg .bubble pre code {
          background: none; padding: 0; font-size: 12px; white-space: pre;
        }
        .da-rag-suggestions {
          display: grid; gap: 6px; margin: 2px 0 12px;
        }
        .da-rag-suggestion {
          width: 100%; padding: 8px 10px; border-radius: 8px; text-align: left;
          border: 1px solid var(--md-default-fg-color--lightest, rgba(127,127,127,.22));
          background: var(--md-default-bg-color--light, var(--md-code-bg-color, #f0f0f0));
          color: inherit; font: inherit; font-size: 12px; line-height: 1.35; cursor: pointer;
        }
        .da-rag-suggestion:hover {
          border-color: var(--md-accent-fg-color, #b9382b);
          background: var(--md-accent-bg-color, var(--md-default-bg-color));
        }
        .da-rag-suggestion:active { transform: translateY(1px); }
        .da-rag-typing { display: inline-flex; align-items: center; gap: 4px; }
        .da-rag-typing-label { margin-right: 2px; }
        .da-rag-typing-dot {
          width: 5px; height: 5px; border-radius: 50%;
          background: var(--md-accent-fg-color, currentColor);
          animation: da-rag-typing 1.2s ease-in-out infinite;
        }
        .da-rag-typing-dot:nth-child(3) { animation-delay: 120ms; }
        .da-rag-typing-dot:nth-child(4) { animation-delay: 240ms; }
        @keyframes da-rag-typing {
          0%, 60%, 100% { opacity: .35; transform: translateY(0); }
          30% { opacity: 1; transform: translateY(-3px); }
        }
        @media (prefers-reduced-motion: reduce) {
          .da-rag-typing-dot { animation: none; opacity: .75; }
          .da-rag-suggestion:active { transform: none; }
          #da-rag-bubble, #da-rag-bubble .da-rag-trigger-icon, #da-rag-bubble .da-rag-trigger-label { transition: none; }
          #da-rag-bubble.is-snapping { transition: none; }
        }
        .da-rag-sources { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin-top: 9px; font-size: 10px; }
        .da-rag-source-label { color: var(--md-default-fg-color--light); font-weight: 600; }
        .da-rag-source-chip {
          display: inline-flex; box-sizing: border-box; min-width: 0; max-width: min(100%, 220px);
          overflow: hidden; padding: 2px 8px; border: 1px solid var(--md-default-fg-color--lightest, #d8d6e2);
          border-radius: 999px; background: var(--md-default-bg-color--light, #f0eff7);
          color: var(--md-default-fg-color, #242238); text-decoration: none; white-space: nowrap;
          text-overflow: ellipsis; font-size: 10.5px; line-height: 1.5;
          transition: border-color 150ms ease, background-color 150ms ease, color 150ms ease;
        }
        .da-rag-source-chip:hover { border-color: var(--da-rag-focus-color, #3349B4); color: var(--da-rag-focus-color, #3349B4); }
        .da-rag-source-chip:focus-visible { outline: 2px solid var(--da-rag-focus-color, #3349B4); outline-offset: 2px; }
        #da-rag-input-row {
          box-sizing: border-box; display: flex; align-items: center; gap: 8px; min-width: 0;
          padding: 10px 12px 12px; border-top: 1px solid var(--da-rag-header-border, #dedce8);
          background: var(--md-default-bg-color, #fff);
        }
        #da-rag-input {
          box-sizing: border-box; flex: 1 1 auto; min-width: 0; width: 100%; height: 42px;
          border: 1px solid var(--da-rag-input-border, #d8d6e2); border-radius: 16px;
          padding: 9px 12px; outline: none; background: transparent; color: inherit;
          font: inherit; font-size: 13px; line-height: 1.5;
          transition: border-color 150ms ease, box-shadow 150ms ease;
        }
        #da-rag-input::placeholder { color: var(--md-default-fg-color--light, #6b6878); opacity: 1; }
        #da-rag-input:focus { border-color: var(--da-rag-focus-color, #3349B4); box-shadow: 0 0 0 1px var(--da-rag-focus-color, #3349B4); }
        #da-rag-send {
          box-sizing: border-box; flex: 0 0 42px; width: 42px; height: 42px;
          display: grid; place-items: center; padding: 0; border: 0; border-radius: 12px;
          background: transparent; color: var(--da-rag-focus-color, #3349B4); cursor: pointer;
          transition: background-color 150ms ease, transform 120ms ease-out;
        }
        #da-rag-send:hover:not(:disabled) { background: color-mix(in srgb, var(--da-rag-focus-color, #3349B4) 12%, transparent); }
        #da-rag-send:active:not(:disabled) { transform: scale(.96); }
        #da-rag-send svg { width: 19px; height: 19px; display: block; }
        #da-rag-send:disabled { cursor: wait; opacity: 0.45; }
        .da-rag-loading { opacity: 0.6; font-style: italic; }
        @media (max-width: 480px) {
          #da-rag-bubble { bottom: 14px; right: 14px; width: 48px; height: 48px; padding: 0; }
          #da-rag-bubble.is-compact { width: 48px; padding: 0; }
          #da-rag-bubble .da-rag-trigger-label { display: none; }
          #da-rag-header { cursor: default; touch-action: auto; }
          #da-rag-widget {
            box-sizing: border-box;
            left: env(safe-area-inset-left, 0px);
            right: env(safe-area-inset-right, 0px);
            bottom: env(safe-area-inset-bottom, 0px);
            width: auto; max-width: none;
            height: 85vh; height: 85dvh; max-height: 85vh; max-height: 85dvh;
            border-radius: 16px 16px 0 0; transform-origin: bottom center;
          }
        }
      `;
      document.head.appendChild(style);
    }

    const bubble = document.createElement("button");
    bubble.id = "da-rag-bubble";
    bubble.type = "button";
    bubble.title = "Abrir assistente";
    bubble.setAttribute("aria-label", "Abrir assistente");
    bubble.innerHTML = `
      <svg class="da-rag-trigger-icon da-rag-trigger-chat" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false">
        <path d="M5.25 5.5h13.5A2.25 2.25 0 0 1 21 7.75v7.5a2.25 2.25 0 0 1-2.25 2.25h-7.1l-4.9 3v-3H5.25A2.25 2.25 0 0 1 3 15.25v-7.5A2.25 2.25 0 0 1 5.25 5.5Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>
        <path d="m17.2 2.6.75 1.8 1.8.75-1.8.75-.75 1.8-.75-1.8-1.8-.75 1.8-.75.75-1.8Z" fill="currentColor"/>
      </svg>
      <svg class="da-rag-trigger-icon da-rag-trigger-close" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false">
        <path d="m6 6 12 12M18 6 6 18" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
      </svg>
      <span class="da-rag-trigger-label" aria-hidden="true">Pergunte ao assistente</span>
    `;
    document.body.appendChild(bubble);

    const widget = document.createElement("div");
    widget.id = "da-rag-widget";
    widget.setAttribute("role", "dialog");
    widget.setAttribute("aria-modal", "true");
    widget.setAttribute("aria-labelledby", "da-rag-title");
    widget.innerHTML = `
      <div id="da-rag-header">
        <span id="da-rag-title">Assistente do curso</span>
        <div id="da-rag-header-actions">
          <button id="da-rag-new" type="button" aria-label="Nova conversa" title="Nova conversa">
            <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false"><path d="M12 5v14M5 12h14" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="M4 4h16v16H4z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round" opacity=".7"/></svg>
          </button>
          <details id="da-rag-menu">
            <summary aria-label="Opções de posição" title="Opções de posição"><svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" focusable="false"><circle cx="5" cy="12" r="1.7"/><circle cx="12" cy="12" r="1.7"/><circle cx="19" cy="12" r="1.7"/></svg></summary>
            <div id="da-rag-menu-content"><button id="da-rag-reset-position" type="button">Voltar à posição padrão</button></div>
          </details>
          <button id="da-rag-close" type="button" aria-label="Fechar assistente" title="Fechar assistente"><svg viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false"><path d="m6 6 12 12M18 6 6 18" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg></button>
        </div>
      </div>
      <div id="da-rag-messages" aria-live="polite" aria-busy="false"></div>
      <div id="da-rag-input-row">
        <input id="da-rag-input" type="text" placeholder="Pergunte sobre o conteúdo do curso..." aria-label="Pergunta" />
        <button id="da-rag-send" type="button" aria-label="Enviar pergunta" title="Enviar pergunta"><svg viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false"><path d="M4 12 20 4l-5.5 16-3-6.5L4 12Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="M11.5 13.5 20 4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg></button>
      </div>
    `;
    document.body.appendChild(widget);

    function atualizarBotao() {
      bubble.classList.toggle("is-open", estado.aberto);
      bubble.setAttribute("aria-expanded", String(estado.aberto));
    }
    let movimentoPainel = null;
    function animarPainel(abrindo, animar = true) {
      const estiloAntes = getComputedStyle(widget);
      const opacidadeAtual = estiloAntes.opacity;
      const transformacaoAtual = estiloAntes.transform === "none" ? "scale(.95)" : estiloAntes.transform;
      if (movimentoPainel) {
        movimentoPainel.cancel();
        movimentoPainel = null;
      }

      if (abrindo) {
        widget.style.display = "flex";
        widget.classList.remove("closing");
        widget.classList.add("open");
      } else {
        widget.classList.remove("open");
        widget.classList.add("closing");
      }

      const movimentoReduzido = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      if (!animar || movimentoReduzido || typeof widget.animate !== "function") {
        if (!abrindo) {
          widget.classList.remove("closing");
          widget.style.display = "none";
        }
        return;
      }

      const movimento = widget.animate(
        abrindo
          ? [
              { opacity: opacidadeAtual, transform: transformacaoAtual },
              { opacity: 1, transform: "scale(1)" },
            ]
          : [
              { opacity: opacidadeAtual, transform: transformacaoAtual },
              { opacity: 0, transform: "scale(.95)" },
            ],
        {
          duration: abrindo ? 200 : 120,
          easing: "cubic-bezier(.23, 1, .32, 1)",
        }
      );
      movimentoPainel = movimento;
      movimento.onfinish = () => {
        if (movimentoPainel !== movimento) return;
        movimento.cancel();
        movimentoPainel = null;
        if (!abrindo && !estado.aberto) {
          widget.classList.remove("closing");
          widget.style.display = "none";
        }
      };
    }
    atualizarBotao();
    bubble.classList.toggle("is-compact", window.scrollY > 80);
    window.addEventListener("scroll", () => {
      bubble.classList.toggle("is-compact", window.scrollY > 80);
    }, { passive: true });

    const cabecalhoEl = widget.querySelector("#da-rag-header");
    const menuPosicaoEl = widget.querySelector("#da-rag-menu");
    const margemTela = 12;
    const emMobile = () => window.matchMedia("(max-width: 480px)").matches;
    const larguraViewport = () => Math.min(window.innerWidth, document.documentElement.clientWidth || window.innerWidth);
    function aplicarPosicaoBotao(left, top) {
      bubble.style.left = `${left}px`;
      bubble.style.top = `${top}px`;
      bubble.style.right = "auto";
      bubble.style.bottom = "auto";
      bubble.style.setProperty("--da-rag-drag-x", "0px");
      bubble.style.setProperty("--da-rag-drag-y", "0px");
    }
    function restaurarPosicaoBotaoSalva() {
      if (!posicoes.botao || !["esquerda", "direita"].includes(posicoes.botao.lado)) return;
      const largura = bubble.getBoundingClientRect().width;
      const altura = bubble.getBoundingClientRect().height;
      const left = posicoes.botao.lado === "esquerda"
        ? margemTela
        : larguraViewport() - largura - margemTela;
      const top = limitar(Number(posicoes.botao.top) || margemTela, margemTela, window.innerHeight - altura - margemTela);
      aplicarPosicaoBotao(left, top);
      posicoes.botao.top = top;
    }
    function definirPosicaoPainel(left, top) {
      widget.style.left = `${left}px`;
      widget.style.top = `${top}px`;
      widget.style.right = "auto";
      widget.style.bottom = "auto";
    }
    function limitarPosicaoPainel(left, top) {
      const rect = widget.getBoundingClientRect();
      const largura = widget.offsetWidth || rect.width;
      const altura = widget.offsetHeight || rect.height;
      return {
        left: limitar(left, 24, larguraViewport() - largura - 24),
        top: limitar(top, 24, window.innerHeight - altura - 24),
      };
    }
    function aplicarPosicaoPainelSalva() {
      if (!posicoes.painel || emMobile()) return false;
      const displayAntes = widget.style.display;
      const estavaOculto = getComputedStyle(widget).display === "none";
      if (estavaOculto) widget.style.display = "flex";
      widget.style.right = "auto";
      widget.style.bottom = "auto";
      const pos = limitarPosicaoPainel(Number(posicoes.painel.left) || 24, Number(posicoes.painel.top) || 24);
      definirPosicaoPainel(pos.left, pos.top);
      posicoes.painel = pos;
      if (estavaOculto) widget.style.display = displayAntes;
      return true;
    }
    function posicionarPainelPertoDoBotao() {
      if (emMobile()) return;
      const displayAntes = widget.style.display;
      const estavaOculto = getComputedStyle(widget).display === "none";
      if (estavaOculto) widget.style.display = "flex";
      widget.style.left = "auto";
      widget.style.top = "auto";
      widget.style.right = "24px";
      widget.style.bottom = "88px";
      const botaoRect = bubble.getBoundingClientRect();
      const painelRect = widget.getBoundingClientRect();
      const painelLargura = widget.offsetWidth || painelRect.width;
      const painelAltura = widget.offsetHeight || painelRect.height;
      const margemVert = 24;
      const topoAcima = botaoRect.top - painelAltura - 12;
      const topoAbaixo = botaoRect.bottom + 12;
      let topPreferido = topoAcima;
      if (topoAcima < margemVert && topoAbaixo + painelAltura <= window.innerHeight - margemVert) {
        topPreferido = topoAbaixo;
      } else if (topoAcima < margemVert && window.innerHeight - botaoRect.bottom > botaoRect.top) {
        topPreferido = topoAbaixo;
      }
      const leftPreferido = botaoRect.left + botaoRect.width / 2 < larguraViewport() / 2
        ? botaoRect.left
        : botaoRect.right - painelLargura;
      const pos = limitarPosicaoPainel(leftPreferido, topPreferido);
      definirPosicaoPainel(pos.left, pos.top);
      if (estavaOculto) widget.style.display = displayAntes;
    }
    function limparPosicaoPainel() {
      ["left", "top", "right", "bottom"].forEach((prop) => widget.style.removeProperty(prop));
    }

    restaurarPosicaoBotaoSalva();
    if (!emMobile()) aplicarPosicaoPainelSalva();

    let arrasteBotao = null;
    let suprimirCliqueDoArraste = false;
    bubble.addEventListener("pointerdown", (event) => {
      if (!event.isPrimary || (event.pointerType === "mouse" && event.button !== 0)) return;
      const rect = bubble.getBoundingClientRect();
      arrasteBotao = {
        pointerId: event.pointerId,
        x: event.clientX,
        y: event.clientY,
        left: rect.left,
        top: rect.top,
        dx: 0,
        dy: 0,
        moveu: false,
      };
      try { bubble.setPointerCapture(event.pointerId); } catch (_) { /* captura pode não estar disponível */ }
    });
    bubble.addEventListener("pointermove", (event) => {
      if (!arrasteBotao || event.pointerId !== arrasteBotao.pointerId) return;
      const dx = event.clientX - arrasteBotao.x;
      const dy = event.clientY - arrasteBotao.y;
      if (!arrasteBotao.moveu && Math.hypot(dx, dy) <= 5) return;
      arrasteBotao.moveu = true;
      bubble.classList.add("is-dragging");
      const rect = bubble.getBoundingClientRect();
      const left = limitar(arrasteBotao.left + dx, margemTela, larguraViewport() - rect.width - margemTela);
      const top = limitar(arrasteBotao.top + dy, margemTela, window.innerHeight - rect.height - margemTela);
      aplicarPosicaoBotao(arrasteBotao.left, arrasteBotao.top);
      arrasteBotao.dx = left - arrasteBotao.left;
      arrasteBotao.dy = top - arrasteBotao.top;
      bubble.style.setProperty("--da-rag-drag-x", `${arrasteBotao.dx}px`);
      bubble.style.setProperty("--da-rag-drag-y", `${arrasteBotao.dy}px`);
      event.preventDefault();
    });
    function finalizarArrasteBotao(event) {
      if (!arrasteBotao || (event && event.pointerId !== arrasteBotao.pointerId)) return;
      const arraste = arrasteBotao;
      arrasteBotao = null;
      if (!arraste.moveu) return;
      const rect = bubble.getBoundingClientRect();
      const leftAtual = limitar(arraste.left + arraste.dx, margemTela, larguraViewport() - rect.width - margemTela);
      const topAtual = limitar(arraste.top + arraste.dy, margemTela, window.innerHeight - rect.height - margemTela);
      const distanciaEsquerda = leftAtual;
      const distanciaDireita = larguraViewport() - (leftAtual + rect.width);
      const lado = distanciaEsquerda <= distanciaDireita ? "esquerda" : "direita";
      const leftAlvo = lado === "esquerda" ? margemTela : larguraViewport() - rect.width - margemTela;
      const topAlvo = limitar(topAtual, margemTela, window.innerHeight - rect.height - margemTela);
      aplicarPosicaoBotao(leftAlvo, topAlvo);
      posicoes.botao = { lado, top: topAlvo };
      salvarPosicoes();
      bubble.classList.remove("is-dragging");
      bubble.classList.add("is-snapping");
      if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
        bubble.classList.remove("is-snapping");
      } else {
        bubble.style.setProperty("--da-rag-drag-x", `${leftAtual - leftAlvo}px`);
        bubble.style.setProperty("--da-rag-drag-y", `${topAtual - topAlvo}px`);
        bubble.getBoundingClientRect();
        requestAnimationFrame(() => {
          bubble.style.setProperty("--da-rag-drag-x", "0px");
          bubble.style.setProperty("--da-rag-drag-y", "0px");
        });
      }
      suprimirCliqueDoArraste = true;
      window.setTimeout(() => { suprimirCliqueDoArraste = false; }, 300);
    }
    bubble.addEventListener("pointerup", finalizarArrasteBotao);
    bubble.addEventListener("pointercancel", finalizarArrasteBotao);
    bubble.addEventListener("lostpointercapture", finalizarArrasteBotao);
    bubble.addEventListener("transitionend", (event) => {
      if (event.propertyName !== "transform") return;
      bubble.classList.remove("is-snapping");
      bubble.style.setProperty("--da-rag-drag-x", "0px");
      bubble.style.setProperty("--da-rag-drag-y", "0px");
    });

    let arrastePainel = null;
    cabecalhoEl.addEventListener("pointerdown", (event) => {
      if (emMobile() || !event.isPrimary || (event.pointerType === "mouse" && event.button !== 0)) return;
      if (event.target.closest("button, summary, a, input")) return;
      const rect = widget.getBoundingClientRect();
      arrastePainel = {
        pointerId: event.pointerId,
        x: event.clientX,
        y: event.clientY,
        left: rect.left,
        top: rect.top,
        moveu: false,
      };
      try { cabecalhoEl.setPointerCapture(event.pointerId); } catch (_) { /* captura pode não estar disponível */ }
    });
    cabecalhoEl.addEventListener("pointermove", (event) => {
      if (!arrastePainel || event.pointerId !== arrastePainel.pointerId) return;
      const dx = event.clientX - arrastePainel.x;
      const dy = event.clientY - arrastePainel.y;
      if (!arrastePainel.moveu && Math.hypot(dx, dy) <= 5) return;
      arrastePainel.moveu = true;
      cabecalhoEl.classList.add("is-dragging");
      const pos = limitarPosicaoPainel(arrastePainel.left + dx, arrastePainel.top + dy);
      definirPosicaoPainel(pos.left, pos.top);
      event.preventDefault();
    });
    function finalizarArrastePainel(event) {
      if (!arrastePainel || (event && event.pointerId !== arrastePainel.pointerId)) return;
      const arraste = arrastePainel;
      arrastePainel = null;
      cabecalhoEl.classList.remove("is-dragging");
      if (!arraste.moveu) return;
      const rect = widget.getBoundingClientRect();
      posicoes.painel = limitarPosicaoPainel(rect.left, rect.top);
      definirPosicaoPainel(posicoes.painel.left, posicoes.painel.top);
      salvarPosicoes();
    }
    cabecalhoEl.addEventListener("pointerup", finalizarArrastePainel);
    cabecalhoEl.addEventListener("pointercancel", finalizarArrastePainel);
    cabecalhoEl.addEventListener("lostpointercapture", finalizarArrastePainel);

    window.addEventListener("resize", () => {
      if (posicoes.botao) restaurarPosicaoBotaoSalva();
      if (emMobile()) {
        limparPosicaoPainel();
      } else if (posicoes.painel) {
        aplicarPosicaoPainelSalva();
        if (estado.aberto) widget.style.display = "flex";
      } else if (estado.aberto) {
        posicionarPainelPertoDoBotao();
      } else {
        limparPosicaoPainel();
      }
      salvarPosicoes();
    });

    widget.querySelector("#da-rag-reset-position").addEventListener("click", () => {
      delete posicoes.botao;
      delete posicoes.painel;
      try { localStorage.removeItem(POSITION_KEY); } catch (_) { /* posição padrão continua disponível */ }
      ["left", "top", "right", "bottom"].forEach((prop) => bubble.style.removeProperty(prop));
      bubble.style.setProperty("--da-rag-drag-x", "0px");
      bubble.style.setProperty("--da-rag-drag-y", "0px");
      bubble.classList.remove("is-dragging", "is-snapping");
      limparPosicaoPainel();
      menuPosicaoEl.open = false;
      if (estado.aberto && !emMobile()) posicionarPainelPertoDoBotao();
    });

    const inputEl = widget.querySelector("#da-rag-input");
    const sendButton = widget.querySelector("#da-rag-send");
    const messagesEl = widget.querySelector("#da-rag-messages");

    // Restaura conversa e estado aberto/fechado de antes da navegação.
    // Usamos o messagesEl ATUAL (widget recém-montado) explicitamente aqui,
    // já que é a única vez que precisamos de uma referência direta — o
    // resto do código (addMessage) sempre busca o container atual de novo.
    estado.mensagens.forEach((m) => renderizarMensagem(messagesEl, m));
    if (estado.aberto) {
      if (!emMobile() && !aplicarPosicaoPainelSalva()) posicionarPainelPertoDoBotao();
      animarPainel(true, false);
      atualizarBotao();
      if (estado.mensagens.length === 0) {
        addMessage(MENSAGEM_BOAS_VINDAS, "bot", null, false, true);
      }
      inputEl.focus();
    }
    mostrarSugestoes(messagesEl);

    function fecharWidget() {
      estado.aberto = false;
      animarPainel(false);
      salvarEstado();
      atualizarBotao();
      bubble.focus();
    }

    widget.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        fecharWidget();
        return;
      }
      if (event.key !== "Tab") return;

      const focaveis = Array.from(widget.querySelectorAll(
        'button:not(:disabled), input:not(:disabled), a[href], [tabindex]:not([tabindex="-1"])'
      )).filter((el) => el.getClientRects().length > 0);
      if (focaveis.length === 0) {
        event.preventDefault();
        return;
      }
      const primeiro = focaveis[0];
      const ultimo = focaveis[focaveis.length - 1];
      if (event.shiftKey && (document.activeElement === primeiro || !widget.contains(document.activeElement))) {
        event.preventDefault();
        ultimo.focus();
      } else if (!event.shiftKey && (document.activeElement === ultimo || !widget.contains(document.activeElement))) {
        event.preventDefault();
        primeiro.focus();
      }
    });

    async function enviarPergunta(perguntaInformada, retryOf) {
      const pergunta = typeof perguntaInformada === "string" ? perguntaInformada.trim() : inputEl.value.trim();
      if (!pergunta || estado.enviando) return;
      if (retryOf) {
        removeMessage(retryOf.errorMessageId);
        removeMessage(retryOf.userMessageId);
      }
      const mensagensParaHistorico = estado.mensagens
        .filter((m) => !m.loading && !m.boasVindas && (m.who === "user" || m.who === "bot"))
        .filter((m) => !(retryOf && m.id === retryOf.userMessageId));
      const historico = mensagensParaHistorico
        .slice(-MAX_HISTORY_MESSAGES)
        .map((m) => ({
          papel: m.who === "bot" ? "assistant" : "user",
          conteudo: m.texto,
        }));
      estado.enviando = true;
      inputEl.disabled = true;
      sendButton.disabled = true;
      messagesEl.setAttribute("aria-busy", "true");
      inputEl.value = "";
      const userMessageId = addMessage(pergunta, "user");
      estado.perguntaPendente = pergunta;
      estado.mensagemUsuarioPendente = userMessageId;

      messagesEl.querySelector(".da-rag-suggestions")?.remove();
      const loadingId = addMessage("Digitando", "bot", null, true);
      salvarEstado();

      try {
        const apiUrl = obterUrlApi();
        const body = { pergunta, historico };
        if (estado.conversaId && estado.conversaToken) {
          body.conversa_id = estado.conversaId;
          body.conversa_token = estado.conversaToken;
        }
        const resp = await fetch(apiUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        if (!resp.ok) {
          let detalhe = "";
          try {
            const erroApi = await resp.json();
            detalhe = typeof erroApi.detail === "string" ? erroApi.detail : typeof erroApi.erro === "string" ? erroApi.erro : "";
          } catch (_) { /* resposta pode não ser JSON */ }
          const descricoes = {
            401: "A API recusou a autenticação (HTTP 401). Confira as credenciais e permissões do servidor.",
            403: "A API negou o acesso (HTTP 403). Confira as permissões e a configuração de acesso.",
            404: "A rota da API não foi encontrada (HTTP 404). Confira se a URL configurada termina na rota /ask.",
          };
          throw new Error(descricoes[resp.status] || `A API respondeu com HTTP ${resp.status}.${detalhe ? ` Detalhe: ${detalhe}` : ""}`);
        }
        let data;
        try {
          data = await resp.json();
        } catch (_) {
          throw new Error("A API respondeu, mas enviou um conteúdo que não está em JSON válido.");
        }

        removeMessage(loadingId);
        if (typeof data.conversa_id === "string" && typeof data.conversa_token === "string") {
          estado.conversaId = data.conversa_id;
          estado.conversaToken = data.conversa_token;
        }

        if (data.erro) {
          throw new Error(`A API não conseguiu responder: ${data.erro}`);
        } else if (data.detail) {
          throw new Error(`A API não conseguiu responder: ${data.detail}`);
        } else if (typeof data.resposta !== "string") {
          throw new Error("A API retornou uma resposta sem o campo de texto esperado.");
        } else {
          estado.perguntaPendente = null;
          estado.mensagemUsuarioPendente = null;
          if (typeof data.conversa_id === "string" && typeof data.conversa_token === "string") {
            estado.conversaId = data.conversa_id;
            estado.conversaToken = data.conversa_token;
          }
          addMessage(data.resposta, "bot", validarFontes(data.fontes));
        }
      } catch (e) {
        removeMessage(loadingId);
        estado.perguntaPendente = null;
        estado.mensagemUsuarioPendente = null;
        const explicacao = e instanceof TypeError
          ? "Não foi possível conectar à API do chat. Verifique se o endereço está correto, se o servidor está online e se o CORS permite este site."
          : (e && e.message) || "Ocorreu um erro inesperado ao consultar a API.";
        addMessage(explicacao, "bot", null, false, false, {
          retryQuestion: pergunta,
          retryUserMessageId: userMessageId,
        });
      } finally {
        estado.enviando = false;
        // Estes elementos podem já não ser os "atuais" se o widget foi
        // recriado durante o fetch (navegação no meio da pergunta) — nesse
        // caso agir sobre eles é inofensivo (ficam órfãos, sem efeito
        // visual), e o widget novo já nasce com enviando=false de qualquer
        // forma, então não há travamento.
        inputEl.disabled = false;
        sendButton.disabled = false;
        messagesEl.setAttribute("aria-busy", "false");
        document.querySelectorAll(".da-rag-retry").forEach((button) => { button.disabled = false; });
        salvarEstado();
        const inputAtual = document.getElementById("da-rag-input");
        if (estado.aberto && inputAtual) inputAtual.focus();
      }
    }

    bubble.addEventListener("click", (event) => {
      if (suprimirCliqueDoArraste) {
        event.preventDefault();
        return;
      }
      if (estado.aberto) {
        fecharWidget();
        return;
      }
      estado.aberto = true;
      if (!emMobile() && !aplicarPosicaoPainelSalva()) posicionarPainelPertoDoBotao();
      animarPainel(true);
      salvarEstado();
      atualizarBotao();
      if (estado.mensagens.length === 0) {
        addMessage(MENSAGEM_BOAS_VINDAS, "bot", null, false, true);
      }
      mostrarSugestoes(messagesEl);
      inputEl.focus();
    });
    widget.querySelector("#da-rag-new").addEventListener("click", () => {
      if (estado.enviando) return;
      estado.mensagens = [];
      estado.conversaId = null;
      estado.conversaToken = null;
      estado.perguntaPendente = null;
      estado.mensagemUsuarioPendente = null;
      const mensagensAtual = document.getElementById("da-rag-messages");
      if (mensagensAtual) mensagensAtual.replaceChildren();
      addMessage(MENSAGEM_BOAS_VINDAS, "bot", null, false, true);
      mostrarSugestoes(mensagensAtual);
      salvarEstado();
      inputEl.focus();
    });
    widget.querySelector("#da-rag-close").addEventListener("click", fecharWidget);
    sendButton.addEventListener("click", enviarPergunta);
    messagesEl.addEventListener("click", (event) => {
      const suggestion = event.target.closest(".da-rag-suggestion");
      if (suggestion && !estado.enviando) {
        enviarPergunta(suggestion.textContent);
        return;
      }
      const retryButton = event.target.closest(".da-rag-retry");
      if (!retryButton || estado.enviando) return;
      const erro = estado.mensagens.find((m) => String(m.id) === retryButton.dataset.retryMessageId);
      if (!erro || !erro.retryQuestion) return;
      retryButton.disabled = true;
      enviarPergunta(erro.retryQuestion, {
        errorMessageId: erro.id,
        userMessageId: erro.retryUserMessageId,
      });
    });
    inputEl.addEventListener("keydown", (e) => {
      if (e.key === "Enter") enviarPergunta();
    });
  }

  // --- Funções de mensagem, fora de montarWidget ---------------------------
  // Ficam no escopo do módulo (não dentro de montarWidget) de propósito:
  // se o widget for recriado no meio de uma pergunta (o aluno navegou pra
  // outra página enquanto o fetch ainda estava em andamento), a resposta
  // não pode ficar "presa" a um container antigo e desconectado do DOM.
  // Por isso addMessage/renderizarMensagem sempre buscam o container ATUAL
  // via document.getElementById, nunca uma referência guardada de antes.
  let proximoId = 1;

  function restaurarEstado() {
    try {
      const salvo = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || "null");
      if (!salvo || typeof salvo !== "object") return;
      estado.aberto = !!salvo.aberto;
      estado.mensagens = Array.isArray(salvo.mensagens)
        ? salvo.mensagens.filter((m) => m && Number.isInteger(m.id) && typeof m.texto === "string" && ["user", "bot"].includes(m.who))
          .slice(-80).map((m) => ({
            id: m.id,
            texto: m.texto.slice(0, 20000),
            who: m.who,
            fontes: validarFontes(m.fontes),
            loading: false,
            boasVindas: !!m.boasVindas,
            retryQuestion: typeof m.retryQuestion === "string" ? m.retryQuestion.slice(0, 4000) : null,
            retryUserMessageId: Number.isInteger(m.retryUserMessageId) ? m.retryUserMessageId : null,
          }))
        : [];
      estado.conversaId = typeof salvo.conversaId === "string" ? salvo.conversaId : null;
      estado.conversaToken = typeof salvo.conversaToken === "string" ? salvo.conversaToken : null;
      estado.perguntaPendente = typeof salvo.perguntaPendente === "string" ? salvo.perguntaPendente.slice(0, 4000) : null;
      estado.mensagemUsuarioPendente = Number.isInteger(salvo.mensagemUsuarioPendente) ? salvo.mensagemUsuarioPendente : null;
      proximoId = estado.mensagens.reduce((maior, m) => Math.max(maior, m.id), 0) + 1;

      if (estado.perguntaPendente) {
        const pergunta = estado.perguntaPendente;
        const userMessageId = estado.mensagemUsuarioPendente;
        estado.perguntaPendente = null;
        estado.mensagemUsuarioPendente = null;
      if (!estado.mensagens.some((m) => m.id === userMessageId) && userMessageId !== null) {
        estado.mensagens.push({
          id: userMessageId,
          texto: pergunta,
          who: "user",
          fontes: [],
          loading: false,
          boasVindas: false,
          retryQuestion: null,
          retryUserMessageId: null,
        });
      }
        estado.mensagens.push({
          id: proximoId++,
          texto: "A pergunta foi interrompida ao trocar de página ou recarregar. Tente novamente quando quiser.",
          who: "bot",
          fontes: [],
          loading: false,
          boasVindas: false,
          retryQuestion: pergunta,
          retryUserMessageId: userMessageId,
        });
      }
      salvarEstado();
    } catch (_) {
      // Storage indisponível ou dados antigos/inválidos: inicia conversa vazia.
    }
  }

  // Conversor leve de markdown -> HTML (escapa HTML primeiro, por segurança,
  // e só então aplica as transformações de markdown mais comuns).
  function markdownParaHtml(texto) {
    let seguro = texto
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");

    // Blocos de código ```linguagem\ncódigo\n``` -> <pre><code>, ANTES de
    // qualquer outra transformação (senão o conteúdo do código seria
    // interpretado como markdown também, ex: um "*" dentro do código).
    // Guardamos cada bloco num array e substituímos por um placeholder,
    // pra reinserir intacto no final (depois de processar o resto do texto).
    const blocosDeCodigo = [];
    seguro = seguro.replace(/```[a-zA-Z]*\n?([\s\S]*?)```/g, (_, codigo) => {
      const idx = blocosDeCodigo.length;
      blocosDeCodigo.push(codigo.replace(/\n$/, ""));
      return `%%CODEBLOCK_${idx}%%`;
    });

    seguro = seguro.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    seguro = seguro.replace(/__(.+?)__/g, "<strong>$1</strong>");
    seguro = seguro.replace(/\*(.+?)\*/g, "<em>$1</em>");
    seguro = seguro.replace(/(?<!\w)_(.+?)_(?!\w)/g, "<em>$1</em>");
    seguro = seguro.replace(/`(.+?)`/g, "<code>$1</code>");
    seguro = seguro.replace(/^#{1,6}\s+(.+)$/gm, "<strong>$1</strong>");

    const linhas = seguro.split("\n");
    let html = "";
    let dentroLista = false;
    for (const linha of linhas) {
      const itemLista = linha.match(/^\s*[-*]\s+(.+)$/);
      if (itemLista) {
        if (!dentroLista) {
          html += "<ul>";
          dentroLista = true;
        }
        html += `<li>${itemLista[1]}</li>`;
      } else {
        if (dentroLista) {
          html += "</ul>";
          dentroLista = false;
        }
        html += linha.trim() ? `<p>${linha}</p>` : "";
      }
    }
    if (dentroLista) html += "</ul>";

    // Reinsere os blocos de código no lugar dos placeholders
    html = html.replace(/%%CODEBLOCK_(\d+)%%/g, (_, idx) => {
      return `<pre><code>${blocosDeCodigo[Number(idx)]}</code></pre>`;
    });

    return html;
  }

  function validarFontes(fontes) {
    if (!Array.isArray(fontes)) return [];
    const unicas = new Map();
    fontes.forEach((fonte) => {
      if (!fonte || typeof fonte.url !== "string") return false;
      try {
        const url = new URL(fonte.url);
        const valida = (
          url.protocol === "https:" &&
          url.hostname === SITE_HOST &&
          url.pathname.startsWith(SITE_PATH) &&
          !url.username &&
          !url.password
        );
        if (valida && !unicas.has(url.href)) {
          unicas.set(url.href, {
            titulo: typeof fonte.titulo === "string" ? fonte.titulo : url.href,
            url: url.href,
          });
        }
      } catch (e) {
        // Ignora fontes inválidas.
      }
    });
    return Array.from(unicas.values());
  }

  function renderizarMensagem(container, m) {
    const wrap = document.createElement("div");
    wrap.className = `da-rag-msg ${m.who}`;
    if (m.retryQuestion) wrap.classList.add("error");
    wrap.dataset.msgId = m.id;
    const bubbleEl = document.createElement("div");
    bubbleEl.className = "bubble";
    if (m.loading) {
      bubbleEl.classList.add("da-rag-loading");
      bubbleEl.setAttribute("role", "status");
      bubbleEl.setAttribute("aria-label", "Assistente digitando");
      const typing = document.createElement("span");
      typing.className = "da-rag-typing";
      const label = document.createElement("span");
      label.className = "da-rag-typing-label";
      label.textContent = "Digitando";
      typing.appendChild(label);
      for (let index = 0; index < 3; index += 1) {
        const dot = document.createElement("span");
        dot.className = "da-rag-typing-dot";
        dot.setAttribute("aria-hidden", "true");
        typing.appendChild(dot);
      }
      bubbleEl.appendChild(typing);
    } else if (m.who === "bot") {
      // innerHTML aqui é seguro: markdownParaHtml escapa < > & antes de
      // aplicar as tags, então não dá pra injetar HTML arbitrário.
      bubbleEl.innerHTML = markdownParaHtml(m.texto);
    } else {
      bubbleEl.textContent = m.texto;
    }
    wrap.appendChild(bubbleEl);

    if (m.retryQuestion) {
      const retry = document.createElement("button");
      retry.type = "button";
      retry.className = "da-rag-retry";
      retry.dataset.retryMessageId = String(m.id);
      retry.textContent = "Tentar novamente";
      wrap.appendChild(retry);
    }

    if (m.fontes && m.fontes.length) {
      const src = document.createElement("div");
      src.className = "da-rag-sources";
      const label = document.createElement("span");
      label.className = "da-rag-source-label";
      label.textContent = "Fontes";
      src.appendChild(label);
      validarFontes(m.fontes).forEach((f) => {
        const link = document.createElement("a");
        link.className = "da-rag-source-chip";
        link.href = f.url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = f.titulo || f.url;
        link.title = f.titulo || f.url;
        src.appendChild(link);
      });
      wrap.appendChild(src);
    }

    container.appendChild(wrap);
    container.scrollTop = container.scrollHeight;
    return wrap;
  }

  /** Adiciona mensagem ao estado E ao container atual do DOM (se existir). */
  function addMessage(texto, who, fontes, loading, boasVindas, metadados) {
    const id = proximoId++;
    const m = {
      id, texto, who, fontes: validarFontes(fontes), loading: !!loading, boasVindas: !!boasVindas,
      retryQuestion: metadados && metadados.retryQuestion,
      retryUserMessageId: metadados && metadados.retryUserMessageId,
    };
    estado.mensagens.push(m);

    const container = document.getElementById("da-rag-messages");
    if (container) renderizarMensagem(container, m);
    salvarEstado();

    return id;
  }

  /** Remove mensagem do estado E do DOM atual (se ainda estiver lá). */
  function removeMessage(id) {
    if (!Number.isInteger(id)) return;
    estado.mensagens = estado.mensagens.filter((m) => m.id !== id);
    const el = document.querySelector(`[data-msg-id="${id}"]`);
    if (el) el.remove();
    salvarEstado();
  }

  // O site usa navegação de página normal (sem navigation.instant), então
  // este script é executado novamente a cada página. Inicializamos após o
  // DOM ficar pronto para garantir que document.body já exista.
  restaurarEstado();
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", montarWidget, { once: true });
  } else {
    montarWidget();
  }
})();
