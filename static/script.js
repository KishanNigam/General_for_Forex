(() => {
  "use strict";

  const REMINDER_DELAY = 120000;
  const $ = (selector) => document.querySelector(selector);
  const dashboard = $("#dashboard-view");
  const journal = $("#journal-view");
  const generalDialog = $("#general-dialog");
  const tradeDialog = $("#trade-dialog");
  const rulesDialog = $("#rules-dialog");
  let generals = [];
  let trades = [];
  let currentGeneralId = null;
  let editingTradeId = null;
  let rulesReminder = null;
  let messageTimeout = null;

  async function api(url, options = {}) {
    const response = await fetch(url, {
      ...options,
      headers: { "Content-Type": "application/json", ...(options.headers || {}) }
    });
    let result = null;
    if (response.status !== 204) {
      try {
        result = await response.json();
      } catch {
        throw new Error(
          response.ok
            ? "The server returned an invalid response."
            : `The server could not complete the request (HTTP ${response.status}).`
        );
      }
    }
    if (!response.ok) throw new Error(result?.error || `Request failed (${response.status}).`);
    return result;
  }
  function showMessage(message, isError = false) {
    const box = $("#app-message");
    box.textContent = message;
    box.classList.toggle("error", isError);
    box.hidden = false;
    clearTimeout(messageTimeout);
    messageTimeout = setTimeout(() => { box.hidden = true; }, 3500);
  }

  function localToday() {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  }

  function currentGeneral() {
    return generals.find((general) => general.id === currentGeneralId) || null;
  }

  function makeButton(label, className, action, id) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = className;
    button.textContent = label;
    button.dataset.action = action;
    if (id) button.dataset.id = id;
    return button;
  }

  function renderGenerals() {
    const list = $("#general-list");
    list.replaceChildren();
    $("#general-count").textContent = String(generals.length);
    $("#dashboard-empty").hidden = generals.length !== 0;
    for (const general of generals) {
      const card = document.createElement("article");
      card.className = "general-card";
      const title = document.createElement("h2");
      title.className = "card-title";
      title.textContent = general.name;
      const meta = document.createElement("p");
      meta.className = "card-meta";
      const count = trades.filter((trade) => trade.general_id === general.id).length;
      const capital = general.starting_capital !== null
        && general.starting_capital !== undefined
        && Number.isFinite(Number(general.starting_capital))
        ? ` · Starting capital ${formatMoney(Number(general.starting_capital))}`
        : "";
      meta.textContent = `${count} ${count === 1 ? "trade" : "trades"}${capital}`;
      const actions = document.createElement("div");
      actions.className = "card-actions";
      actions.append(
        makeButton("Open", "button button-secondary", "open-general", general.id),
        makeButton("Rename", "text-button", "rename-general", general.id),
        makeButton("Delete", "text-button danger", "delete-general", general.id)
      );
      card.append(title, meta, actions);
      list.append(card);
    }
  }

  function renderTrades() {
    const ownTrades = trades.filter((trade) => trade.general_id === currentGeneralId);
    const body = $("#trade-list");
    body.replaceChildren();
    ownTrades.forEach((trade, index) => {
      const row = document.createElement("tr");
      const pnl = recordedPnl(trade);
      row.classList.add(pnl === null ? "pnl-neutral" : pnl > 0 ? "pnl-positive" : pnl < 0 ? "pnl-negative" : "pnl-neutral");
      const values = [
        index + 1,
        trade.date,
        trade.pair,
        trade.side,
        trade.lot,
        trade.entry,
        trade.exit,
        trade.capital_after_target,
        pnl === null ? "Not recorded" : signedMoney(pnl),
        trade.emotion
      ];
      values.forEach((value, column) => {
        const cell = document.createElement("td");
        if (column === 3) {
          const badge = document.createElement("span");
          badge.className = `side-badge ${trade.side === "BUY" ? "side-buy" : "side-sell"}`;
          badge.textContent = trade.side;
          cell.append(badge);
        } else {
          cell.textContent = String(value);
        }
        row.append(cell);
      });
      const actions = document.createElement("td");
      actions.className = "trade-actions";
      actions.append(
        makeButton("Edit", "text-button", "edit-trade", trade.id),
        makeButton("Delete", "text-button danger", "delete-trade", trade.id)
      );
      row.append(actions);
      body.append(row);
    });
    $("#trade-count").textContent = `${ownTrades.length} ${ownTrades.length === 1 ? "trade" : "trades"}`;
    $("#trades-empty").hidden = ownTrades.length !== 0;
    renderPnlSummary(ownTrades);
  }

  function formatMoney(value) {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    }).format(value);
  }

  function signedMoney(value) {
    if (value > 0) return `+${formatMoney(value)}`;
    if (value < 0) return `-${formatMoney(Math.abs(value))}`;
    return formatMoney(0);
  }

  function recordedPnl(trade) {
    if (trade.pnl === undefined || trade.pnl === null || trade.pnl === "") return null;
    const value = Number(trade.pnl);
    return Number.isFinite(value) ? value : null;
  }

  function renderPnlSummary(ownTrades) {
    const pnlValues = ownTrades.map(recordedPnl);
    const recordedValues = pnlValues.filter((value) => value !== null);
    const profit = recordedValues.reduce((sum, value) => sum + Math.max(value, 0), 0);
    const loss = recordedValues.reduce((sum, value) => sum + Math.abs(Math.min(value, 0)), 0);
    const missingCount = pnlValues.length - recordedValues.length;
    const general = currentGeneral();
    const hasStartingCapital = general
      && general.starting_capital !== undefined
      && general.starting_capital !== null
      && Number.isFinite(Number(general.starting_capital));

    $("#total-profit").textContent = recordedValues.length || ownTrades.length === 0
      ? signedMoney(profit)
      : "Not recorded";
    $("#total-loss").textContent = recordedValues.length || ownTrades.length === 0
      ? signedMoney(-loss)
      : "Not recorded";

    const totalMagnitude = profit + loss;
    const circumference = 2 * Math.PI * 91;
    const profitLength = totalMagnitude ? circumference * (profit / totalMagnitude) : 0;
    const lossLength = totalMagnitude ? circumference * (loss / totalMagnitude) : 0;
    $("#meter-profit-arc").setAttribute("stroke-dasharray", `${profitLength} ${circumference}`);
    $("#meter-loss-arc").setAttribute("stroke-dasharray", `${lossLength} ${circumference}`);
    $("#meter-loss-arc").setAttribute("stroke-dashoffset", String(-profitLength));
    $("#meter-profit-arc").style.opacity = profitLength > 0 ? "1" : "0";
    $("#meter-loss-arc").style.opacity = lossLength > 0 ? "1" : "0";
    $("#meter-description").textContent =
      `Recorded profit ${formatMoney(profit)} and recorded loss ${formatMoney(loss)}.`;

    const incomplete = missingCount > 0;
    const totalCapital = hasStartingCapital && !incomplete
      ? Number(general.starting_capital) + profit - loss
      : null;
    $("#total-capital").textContent = totalCapital === null
      ? (hasStartingCapital ? "Incomplete data" : "Not set")
      : formatMoney(totalCapital);
    $("#capital-status").textContent = totalCapital !== null
      ? `Starting ${formatMoney(Number(general.starting_capital))}`
      : incomplete
        ? `${missingCount} ${missingCount === 1 ? "trade" : "trades"} missing P&L`
        : "Set starting capital";
    const incompleteNotice = $("#pnl-incomplete");
    incompleteNotice.textContent = incomplete
      ? `${missingCount} ${missingCount === 1 ? "trade has" : "trades have"} no recorded P&L. Total capital is incomplete.`
      : "";
    incompleteNotice.hidden = !incomplete;
  }

  function navigateToGeneral(generalId, updateHistory = true) {
    const general = generals.find((item) => item.id === generalId);
    if (!general) {
      currentGeneralId = null;
      dashboard.hidden = false;
      journal.hidden = true;
      if (updateHistory && location.hash) history.replaceState(null, "", location.pathname + location.search);
      return;
    }
    currentGeneralId = generalId;
    dashboard.hidden = true;
    journal.hidden = false;
    $("#journal-title").textContent = general.name;
    renderTrades();
    if (updateHistory && location.hash !== `#general=${encodeURIComponent(generalId)}`) {
      history.pushState(null, "", `#general=${encodeURIComponent(generalId)}`);
    }
  }

  function refreshView() {
    renderGenerals();
    if (currentGeneral()) {
      $("#journal-title").textContent = currentGeneral().name;
      renderTrades();
    } else {
      navigateToGeneral(null, false);
    }
  }

  function clearFieldError(selector) {
    const error = $(selector);
    error.textContent = "";
    error.hidden = true;
  }

  function setFieldError(selector, message) {
    const error = $(selector);
    error.textContent = message;
    error.hidden = false;
  }

  function openGeneralForm(general = null) {
    $("#general-form").reset();
    clearFieldError("#general-error");
    $("#general-dialog-title").textContent = general ? "Edit General" : "Add General";
    $("#general-save-button").textContent = general ? "Save Name" : "Save";
    $("#general-name").value = general?.name || "";
    $("#general-starting-capital").value =
      general?.starting_capital === undefined || general?.starting_capital === null
        ? ""
        : String(general.starting_capital);
    generalDialog.dataset.generalId = general?.id || "";
    generalDialog.showModal();
    $("#general-name").focus();
  }

  function openTradeForm(trade = null) {
    const ownTrades = trades.filter((item) => item.general_id === currentGeneralId);
    $("#trade-form").reset();
    clearFieldError("#trade-error");
    editingTradeId = trade?.id || null;
    $("#trade-dialog-title").textContent = trade ? "Edit Trade" : "Add Trade";
    $("#trade-save-button").textContent = trade ? "Save Changes" : "Save Trade";
    $("#trade-number").value = trade?.trade_number ?? ownTrades.length + 1;
    $("#trade-date").value = trade?.date || localToday();
    $("#trade-pair").value = trade?.pair || "XAUUSD";
    $("#trade-side").value = trade?.side || "";
    for (const field of ["lot", "entry", "exit", "capital_after_target"]) {
      $(`#trade-${field === "capital_after_target" ? "capital" : field}`).value =
        trade ? String(trade[field]) : "";
    }
    $("#trade-pnl").value =
      trade?.pnl === undefined || trade?.pnl === null ? "" : String(trade.pnl);
    const emotionSelect = $("#trade-emotion");
    const options = Array.from(emotionSelect.options).map((option) => option.value);
    const isKnownEmotion = trade && options.includes(trade.emotion);
    emotionSelect.value = trade ? (isKnownEmotion ? trade.emotion : "Other") : "";
    $("#custom-emotion").value = trade && !isKnownEmotion ? trade.emotion : "";
    updateCustomEmotion();
    tradeDialog.showModal();
  }

  function updateCustomEmotion() {
    const isOther = $("#trade-emotion").value === "Other";
    $("#custom-emotion-field").hidden = !isOther;
    $("#custom-emotion").required = isOther;
  }

  async function loadState() {
    const state = await api("/api/state");
    generals = state.generals;
    trades = state.trades;
    renderGenerals();
    const hash = location.hash.match(/^#general=(.+)$/);
    const requestedId = hash ? decodeURIComponent(hash[1]) : null;
    if (requestedId && generals.some((general) => general.id === requestedId)) {
      navigateToGeneral(requestedId, false);
    } else {
      navigateToGeneral(null, Boolean(location.hash));
    }
  }

  function openRules() {
    if (rulesDialog.open) return;
    const list = $("#rules-list");
    list.replaceChildren();
    const rules = Array.isArray(window.TRADING_RULES) ? window.TRADING_RULES : [];
    rules.forEach((rule, index) => {
      const item = document.createElement("li");
      const label = document.createElement("label");
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.dataset.ruleIndex = String(index);
      const text = document.createElement("span");
      text.textContent = String(rule);
      label.append(checkbox, text);
      item.append(label);
      list.append(item);
    });
    $("#rules-close-button").disabled = true;
    $("#rules-error").hidden = true;
    rulesDialog.showModal();
  }

  function scheduleRulesReminder() {
    clearTimeout(rulesReminder);
    rulesReminder = setTimeout(() => {
      rulesReminder = null;
      if (!rulesDialog.open) openRules();
    }, REMINDER_DELAY);
  }

  $("#add-general-button").addEventListener("click", () => openGeneralForm());
  $("#general-list").addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    const general = generals.find((item) => item.id === button.dataset.id);
    if (!general) return;
    if (button.dataset.action === "open-general") {
      navigateToGeneral(general.id);
    } else if (button.dataset.action === "rename-general") {
      openGeneralForm(general);
    } else if (button.dataset.action === "delete-general") {
      if (!window.confirm(`Delete "${general.name}"? All of its associated trading records will also be deleted. This cannot be undone.`)) return;
      try {
        await api(`/api/generals/${encodeURIComponent(general.id)}`, { method: "DELETE" });
        generals = generals.filter((item) => item.id !== general.id);
        trades = trades.filter((trade) => trade.general_id !== general.id);
        refreshView();
        showMessage("General and its trading records deleted.");
      } catch (error) {
        showMessage(error.message, true);
      }
    }
  });

  $("#general-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    clearFieldError("#general-error");
    const name = $("#general-name").value.trim();
    const rawCapital = $("#general-starting-capital").value.trim();
    if (!name) {
      setFieldError("#general-error", "Enter a General name.");
      $("#general-name").focus();
      return;
    }
    if (rawCapital !== "" && (!Number.isFinite(Number(rawCapital)) || Number(rawCapital) < 0)) {
      setFieldError("#general-error", "Starting Capital (USD) must be a valid non-negative number.");
      $("#general-starting-capital").focus();
      return;
    }
    const generalId = generalDialog.dataset.generalId;
    const button = $("#general-save-button");
    button.disabled = true;
    try {
      const saved = await api(
        generalId ? `/api/generals/${encodeURIComponent(generalId)}` : "/api/generals",
        {
          method: generalId ? "PATCH" : "POST",
          body: JSON.stringify({
            name,
            starting_capital: rawCapital === "" ? null : Number(rawCapital)
          })
        }
      );
      if (generalId) {
        generals = generals.map((item) => item.id === generalId ? saved : item);
        generalDialog.close();
        refreshView();
        showMessage("General renamed.");
      } else {
        generals.push(saved);
        generalDialog.close();
        refreshView();
        navigateToGeneral(saved.id);
        showMessage("General created.");
      }
    } catch (error) {
      setFieldError("#general-error", error.message);
    } finally {
      button.disabled = false;
    }
  });

  $("#back-button").addEventListener("click", () => navigateToGeneral(null));
  $("#edit-general-button").addEventListener("click", () => {
    if (currentGeneral()) openGeneralForm(currentGeneral());
  });
  $("#add-trade-button").addEventListener("click", () => openTradeForm());
  $("#trade-emotion").addEventListener("change", updateCustomEmotion);

  $("#trade-list").addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    const trade = trades.find(
      (item) => item.id === button.dataset.id && item.general_id === currentGeneralId
    );
    if (!trade) return;
    if (button.dataset.action === "edit-trade") {
      openTradeForm(trade);
    } else if (button.dataset.action === "delete-trade") {
      if (!window.confirm("Delete this trade? This cannot be undone.")) return;
      try {
        await api(
          `/api/generals/${encodeURIComponent(currentGeneralId)}/trades/${encodeURIComponent(trade.id)}`,
          { method: "DELETE" }
        );
        trades = trades.filter((item) => item.id !== trade.id);
        const survivors = trades.filter((item) => item.general_id === currentGeneralId);
        survivors.forEach((item, index) => { item.trade_number = index + 1; });
        refreshView();
        showMessage("Trade deleted.");
      } catch (error) {
        showMessage(error.message, true);
      }
    }
  });

  $("#trade-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    clearFieldError("#trade-error");
    const form = event.currentTarget;
    if (!form.reportValidity()) return;
    const emotionChoice = $("#trade-emotion").value;
    const values = {
      date: $("#trade-date").value,
      pair: $("#trade-pair").value.trim(),
      side: $("#trade-side").value,
      lot: $("#trade-lot").value,
      entry: $("#trade-entry").value,
      exit: $("#trade-exit").value,
      capital_after_target: $("#trade-capital").value,
      pnl: $("#trade-pnl").value,
      emotion: emotionChoice === "Other" ? $("#custom-emotion").value.trim() : emotionChoice
    };
    const requiredValues = [
      values.date,
      values.pair,
      values.side,
      values.lot,
      values.entry,
      values.exit,
      values.capital_after_target,
      values.emotion
    ];
    if (requiredValues.some((value) => value === "")) {
      setFieldError("#trade-error", "Complete every required field. Enter a custom emotion when Other is selected.");
      return;
    }
    if (Number(values.lot) < 0) {
      setFieldError("#trade-error", "Lot cannot be negative.");
      return;
    }
    if (values.pnl !== "" && !Number.isFinite(Number(values.pnl))) {
      setFieldError("#trade-error", "P&L ($) must be a valid number.");
      return;
    }
    values.pnl = values.pnl === "" ? null : Number(values.pnl);
    const button = $("#trade-save-button");
    button.disabled = true;
    try {
      const base = `/api/generals/${encodeURIComponent(currentGeneralId)}/trades`;
      const saved = await api(
        editingTradeId ? `${base}/${encodeURIComponent(editingTradeId)}` : base,
        { method: editingTradeId ? "PUT" : "POST", body: JSON.stringify(values) }
      );
      if (editingTradeId) {
        trades = trades.map((item) => item.id === editingTradeId ? saved : item);
      } else {
        trades.push(saved);
      }
      tradeDialog.close();
      refreshView();
      showMessage(editingTradeId ? "Trade updated." : "Trade saved.");
      editingTradeId = null;
    } catch (error) {
      setFieldError("#trade-error", error.message);
    } finally {
      button.disabled = false;
    }
  });

  document.querySelectorAll("[data-close-dialog]").forEach((button) => {
    button.addEventListener("click", () => {
      const dialog = document.getElementById(button.dataset.closeDialog);
      if (dialog?.open) dialog.close();
    });
  });

  $("#rules-list").addEventListener("change", () => {
    const checkboxes = Array.from($("#rules-list").querySelectorAll('input[type="checkbox"]'));
    const allChecked = checkboxes.length > 0 && checkboxes.every((checkbox) => checkbox.checked);
    $("#rules-close-button").disabled = !allChecked;
    $("#rules-error").hidden = allChecked;
  });

  rulesDialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    if ($("#rules-close-button").disabled) return;
    $("#rules-error").hidden = true;
    rulesDialog.close();
    scheduleRulesReminder();
  });

  $("#rules-close-button").addEventListener("click", () => {
    const checkboxes = Array.from($("#rules-list").querySelectorAll('input[type="checkbox"]'));
    if (checkboxes.length === 0 || checkboxes.some((checkbox) => !checkbox.checked)) {
      $("#rules-error").hidden = false;
      return;
    }
    rulesDialog.close();
    scheduleRulesReminder();
  });

  window.addEventListener("hashchange", () => {
    const match = location.hash.match(/^#general=(.+)$/);
    const id = match ? decodeURIComponent(match[1]) : null;
    navigateToGeneral(id, false);
  });
  window.addEventListener("popstate", () => {
    const match = location.hash.match(/^#general=(.+)$/);
    navigateToGeneral(match ? decodeURIComponent(match[1]) : null, false);
  });

  openRules();
  loadState().catch((error) => {
    showMessage(`Could not load saved data: ${error.message}`, true);
  });
})();
