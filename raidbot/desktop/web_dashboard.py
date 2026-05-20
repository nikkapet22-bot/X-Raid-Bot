from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QUrl, Slot
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

_DASHBOARD_RUNTIME_STYLE = r"""
<style>
  .lux-button:disabled,
  .icon-button:disabled {
    cursor: not-allowed;
    opacity: .42;
    transform: none !important;
    animation: none !important;
  }
  .state-dot.neutral,
  .profile-dot.neutral,
  .activity-status-dot.neutral {
    background: var(--dim);
    box-shadow: 0 0 14px rgba(148, 163, 184, .32);
  }
  .state-dot.warning,
  .profile-dot.warning,
  .activity-status-dot.warning {
    background: var(--orange);
    box-shadow: 0 0 14px rgba(255, 180, 84, .55);
  }
  .state-dot.error,
  .profile-dot.error,
  .activity-status-dot.error {
    background: var(--red);
    box-shadow: 0 0 14px rgba(255, 93, 93, .55);
  }
  .state-dot.warmup,
  .profile-dot.warmup,
  .activity-status-dot.warmup {
    background: var(--purple);
    box-shadow: 0 0 14px rgba(173, 108, 255, .56);
  }
  .profile-card.paused {
    border-color: rgba(255, 180, 84, .34);
  }
  .profile-card.stopped {
    border-color: rgba(255, 93, 93, .32);
    opacity: .82;
  }
  .profile-card.failed .profile-raid-now,
  .profile-card.stopped .profile-raid-now {
    display: none;
  }
  .profile-raid-now {
    position: relative;
    z-index: 1;
    width: 100%;
    min-height: 36px;
    margin-top: 12px;
    font-size: 12px;
    letter-spacing: .08em;
    text-transform: uppercase;
  }
  .profile-error {
    position: relative;
    z-index: 1;
    margin-top: 10px;
    color: var(--muted);
    font-size: 12px;
    line-height: 1.45;
  }
  .empty-state {
    padding: 20px;
    color: var(--muted);
    border: 1px dashed rgba(var(--accent-rgb), .18);
    border-radius: 18px;
    background: rgba(var(--accent-rgb), .035);
  }
  .runtime-field-input {
    width: 100%;
    min-height: 42px;
    padding: 10px 12px;
    color: var(--gold-3);
    border: 1px solid rgba(var(--accent-rgb), .13);
    border-radius: 14px;
    outline: none;
    background: rgba(255, 255, 255, .035);
  }
  .runtime-field-input:focus {
    border-color: rgba(var(--accent-rgb), .42);
    box-shadow: 0 0 0 3px rgba(var(--accent-rgb), .08);
  }
  .runtime-switch-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }
  .runtime-checkbox {
    width: 18px;
    height: 18px;
    accent-color: var(--gold);
    cursor: pointer;
  }
  .template-path {
    display: block;
    margin-top: 8px;
    overflow: hidden;
    color: var(--muted);
    font-family: "JetBrains Mono", "Cascadia Mono", monospace;
    font-size: 10px;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .app-page[data-page="settings"] .page-grid.runtime-wide,
  .app-page[data-page="bot-actions"] .page-grid.runtime-wide,
  .app-page[data-page="troubleshoot"] .page-grid.runtime-wide {
    grid-template-columns: minmax(0, 1fr);
  }
  .capture-preview.has-image {
    display: flex;
    align-items: center;
    justify-content: center;
    border-style: solid;
    background: rgba(2, 6, 23, .40);
  }
  .capture-preview.has-image::before,
  .capture-preview.has-image::after {
    display: none;
  }
  .capture-preview img {
    display: block;
    width: 100%;
    height: 100%;
    object-fit: contain;
    border-radius: 12px;
  }
  .capture-empty {
    position: absolute;
    right: 14px;
    bottom: 12px;
    color: var(--muted);
    font-size: 11px;
    font-weight: 800;
    letter-spacing: .10em;
    text-transform: uppercase;
  }
  .preset-summary {
    display: grid;
    gap: 12px;
    margin: 16px 0;
  }
  .preset-count-card {
    padding: 18px;
    border: 1px solid rgba(var(--accent-rgb), .14);
    border-radius: 18px;
    background: rgba(255, 255, 255, .035);
  }
  .preset-count-card strong {
    display: block;
    color: var(--gold-3);
    font-family: "Fraunces", Georgia, serif;
    font-size: 34px;
    line-height: 1;
  }
  .preset-count-card span {
    display: block;
    margin-top: 8px;
    color: var(--muted);
    font-size: 12px;
    font-weight: 800;
    letter-spacing: .12em;
    text-transform: uppercase;
  }
  .page-ready-timeout-card {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 130px;
    align-items: center;
    gap: 16px;
    margin-top: 18px;
    padding: 18px;
    border: 1px solid rgba(var(--accent-rgb), .14);
    border-radius: 18px;
    background: rgba(255, 255, 255, .035);
  }
  .page-ready-timeout-card strong,
  .page-ready-timeout-card span {
    display: block;
  }
  .page-ready-timeout-card span {
    margin-top: 6px;
    color: var(--muted);
    font-size: 12px;
    line-height: 1.35;
  }
  .activity-feed {
    max-height: 286px;
    overflow-y: auto;
    padding-right: 6px;
    overscroll-behavior: contain;
  }
  .activity-feed::-webkit-scrollbar {
    width: 8px;
  }
  .activity-feed::-webkit-scrollbar-track {
    background: rgba(255, 255, 255, .035);
    border-radius: 999px;
  }
  .activity-feed::-webkit-scrollbar-thumb {
    background: rgba(var(--accent-rgb), .30);
    border-radius: 999px;
  }
  .raid-chart .chart-line {
    stroke-dasharray: none !important;
    stroke-dashoffset: 0 !important;
    animation: none !important;
  }
  body.performance-mode *,
  body.performance-mode *::before,
  body.performance-mode *::after {
    animation: none !important;
    transition-duration: .001ms !important;
    scroll-behavior: auto !important;
    box-shadow: none !important;
    filter: none !important;
    backdrop-filter: none !important;
  }
  body.performance-mode {
    background: #050913 !important;
  }
  body.performance-mode .app-shell,
  body.performance-mode .side-rail,
  body.performance-mode .topbar,
  body.performance-mode .panel,
  body.performance-mode .hero-card,
  body.performance-mode .profile-card,
  body.performance-mode .chart-frame,
  body.performance-mode .command-card {
    background-image: none !important;
  }
  body.performance-mode .chart-pulse,
  body.performance-mode .raid-chart,
  body.performance-mode .chart-y-axis,
  body.performance-mode .chart-axis,
  body.performance-mode .orbital-ring,
  body.performance-mode .orbital-status,
  body.performance-mode .profile-preview,
  body.performance-mode .profile-preview::before,
  body.performance-mode .profile-preview::after,
  body.performance-mode .chart-frame::after,
  body.performance-mode .hero-card::before,
  body.performance-mode .panel::before {
    display: none !important;
  }
  body.performance-mode .profile-card,
  body.performance-mode .panel,
  body.performance-mode .preview-panel,
  body.performance-mode .command-card,
  body.performance-mode .topbar,
  body.performance-mode .side-rail,
  body.performance-mode .chart-frame {
    background: #07101d !important;
    border-color: rgba(184, 167, 122, .16) !important;
  }
  body.performance-mode .hero-card,
  body.performance-mode .chart-frame {
    min-height: 0 !important;
  }
  body.performance-mode .chart-frame {
    padding: 18px !important;
  }
  body.performance-mode .rail-button[data-performance-toggle] {
    color: #46e69f !important;
    border-color: rgba(70, 230, 159, .72) !important;
    background: rgba(70, 230, 159, .18) !important;
    box-shadow: 0 0 24px rgba(70, 230, 159, .30) !important;
  }
  .rail-button.performance-toggle.active {
    color: #46e69f !important;
    border-color: rgba(70, 230, 159, .72) !important;
    background: rgba(70, 230, 159, .18) !important;
    box-shadow: 0 0 24px rgba(70, 230, 159, .30) !important;
  }
  button.list-item {
    width: 100%;
    color: inherit;
    cursor: pointer;
    text-align: left;
  }
  button.list-item.active,
  button.list-item:hover {
    border-color: rgba(var(--accent-rgb), .30);
    background: rgba(var(--accent-rgb), .065);
  }
  @media (prefers-reduced-motion: reduce) {
    *,
    *::before,
    *::after {
      animation-duration: .001ms !important;
      animation-iteration-count: 1 !important;
      transition-duration: .001ms !important;
    }
  }
</style>
"""

_DASHBOARD_RUNTIME_SCRIPT = r"""
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<script>
(() => {
  const state = { bridge: null, latest: null };

  const html = (value) => String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");

  const first = (selector) => document.querySelector(selector);
  const all = (selector) => Array.from(document.querySelectorAll(selector));

  const call = (method, ...args) => {
    const bridge = state.bridge;
    if (!bridge || typeof bridge[method] !== "function") return;
    bridge[method](...args);
  };

  const applyPerformanceMode = (enabled) => {
    document.body.classList.toggle("performance-mode", Boolean(enabled));
    all("[data-performance-toggle]").forEach((button) => {
      const active = Boolean(enabled);
      button.classList.toggle("active", active);
      button.classList.toggle("inactive", !active);
      button.dataset.state = active ? "on" : "off";
      button.setAttribute("aria-pressed", active ? "true" : "false");
      button.setAttribute("title", active ? "Performance mode on" : "Performance mode off");
    });
  };

  const togglePerformanceMode = () => {
    const enabled = !document.body.classList.contains("performance-mode");
    applyPerformanceMode(enabled);
    if (state.latest) {
      renderChart(state.latest);
      renderProfiles(state.latest);
    }
    call("setPerformanceMode", enabled);
  };

  const renderSidebarVersion = (data) => {
    const version = first("[data-app-version]");
    if (!version) return;
    version.textContent = data.appVersion || "";
  };

  document.addEventListener("click", (event) => {
    const target = event.target;
    const button = target && typeof target.closest === "function"
      ? target.closest("[data-performance-toggle]")
      : null;
    if (!button) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    togglePerformanceMode();
  }, true);

  const setButtonBusy = (button, busyText) => {
    if (!button) return;
    if (busyText) button.textContent = busyText;
  };

  const wireButtons = () => {
    const topButtons = all(".top-actions .lux-button");
    if (topButtons[0]) topButtons[0].addEventListener("click", () => call("startBot"));
    if (topButtons[1]) topButtons[1].addEventListener("click", () => call("togglePauseResume"));
    if (topButtons[2]) topButtons[2].addEventListener("click", () => call("stopBot"));

    const commandButtons = all(".command-stack .wide-button");
    if (commandButtons[0]) commandButtons[0].addEventListener("click", () => call("raidNow"));
    if (commandButtons[1]) commandButtons[1].addEventListener("click", () => call("raidNow"));
    if (commandButtons[2]) commandButtons[2].addEventListener("click", () => call("togglePauseResume"));
  };

  const renderPill = (pill, label, variant) => {
    if (!pill) return;
    const dot = pill.querySelector(".state-dot");
    if (dot) dot.className = `state-dot ${variant || ""}`.trim();
    const text = Array.from(pill.childNodes).find((node) => node.nodeType === Node.TEXT_NODE);
    if (text) text.textContent = ` ${label}`;
    else pill.append(` ${label}`);
  };

  const renderTopbar = (data) => {
    first(".topbar .app-subtitle")?.remove();
    renderPill(first(".topbar .state-pill"), data.botStateText || "Stopped", data.botVariant);
    const buttons = all(".top-actions .lux-button");
    if (buttons[0]) buttons[0].disabled = !data.canStart;
    if (buttons[1]) {
      buttons[1].textContent = data.pauseButtonText || "Pause";
      buttons[1].disabled = !data.canPause;
    }
    if (buttons[2]) buttons[2].disabled = !data.canStop;
  };

  const renderCommand = (data) => {
    renderPill(first(".command-card .state-pill"), data.connectionStateText || "Disconnected", data.connectionVariant);
    const buttons = all(".command-stack .wide-button");
    if (buttons[0]) {
      buttons[0].textContent = data.globalRaidNowText || "Raid NOW!";
      buttons[0].disabled = !data.canRaidNow;
    }
    if (buttons[1]) {
      buttons[1].textContent = "Fetch latest Telegram raid";
      buttons[1].disabled = !data.canRaidNow;
    }
    if (buttons[2]) {
      buttons[2].textContent = data.pauseButtonText || "Pause queue after current action";
      buttons[2].disabled = !data.canPause;
    }
    const grid = first(".command-card .mini-status-grid");
    if (!grid) return;
    grid.innerHTML = (data.metrics || []).map((metric) => `
      <div class="mini-status">
        <strong>${html(metric.value)}</strong>
        <span>${html(metric.label)}</span>
      </div>
    `).join("");
  };

  const buildPath = (series, width, height, maxValue, smooth) => {
    const safe = Array.isArray(series) && series.length ? series : [0];
    const points = safe.map((value, index) => {
      const x = safe.length === 1 ? 0 : (index / (safe.length - 1)) * width;
      const y = height - (Math.max(0, Number(value) || 0) / maxValue) * height;
      return [x, y];
    });
    if (points.length === 1 || !smooth) {
      return {
        line: points.map(([x, y], i) => `${i ? "L" : "M"} ${x.toFixed(1)} ${y.toFixed(1)}`).join(" "),
        area: `M ${points[0][0].toFixed(1)} ${height} ` +
          points.map(([x, y]) => `L ${x.toFixed(1)} ${y.toFixed(1)}`).join(" ") +
          ` L ${points[points.length - 1][0].toFixed(1)} ${height} Z`,
        points,
      };
    }
    let line = `M ${points[0][0].toFixed(1)} ${points[0][1].toFixed(1)}`;
    for (let i = 0; i < points.length - 1; i += 1) {
      const p0 = points[Math.max(0, i - 1)];
      const p1 = points[i];
      const p2 = points[i + 1];
      const p3 = points[Math.min(points.length - 1, i + 2)];
      const c1x = p1[0] + (p2[0] - p0[0]) / 6;
      const c1y = p1[1] + (p2[1] - p0[1]) / 6;
      const c2x = p2[0] - (p3[0] - p1[0]) / 6;
      const c2y = p2[1] - (p3[1] - p1[1]) / 6;
      line += ` C ${c1x.toFixed(1)} ${c1y.toFixed(1)}, ${c2x.toFixed(1)} ${c2y.toFixed(1)}, ${p2[0].toFixed(1)} ${p2[1].toFixed(1)}`;
    }
    const areaPolyline = points
      .map(([x, y], index) => `${index ? "L" : ""} ${x.toFixed(1)} ${y.toFixed(1)}`)
      .join(" ");
    const area = `M ${points[0][0].toFixed(1)} ${height} L ${areaPolyline} L ${points[points.length - 1][0].toFixed(1)} ${height} Z`;
    return { line, area, points };
  };

  const renderChart = (data) => {
    const axis = first(".chart-y-axis");
    if (axis) {
      axis.innerHTML = (data.chartAxis || [10, 7, 5, 2, 0])
        .map((tick) => `<span>${html(tick)}</span>`)
        .join("");
    }
    const axisLabels = first(".chart-axis");
    if (axisLabels) {
      axisLabels.innerHTML = (data.chartTimes || ["00:00", "06:00", "12:00", "18:00", "NOW"])
        .map((tick) => `<span>${html(tick)}</span>`)
        .join("");
    }
    const liveCard = first(".activity-live-card");
    if (liveCard) {
      const label = liveCard.querySelector("span");
      const value = liveCard.querySelector("strong");
      if (label) label.textContent = "LAST RAID";
      if (value) value.textContent = data.lastRaidText || "--";
    }
    const svg = first(".raid-chart");
    if (!svg) return;
    if (document.body.classList.contains("performance-mode")) {
      svg.innerHTML = "";
      return;
    }
    const series = data.chartSeries || [];
    const top = Math.max(1, Number(data.chartMax || 1));
    const width = 900;
    const height = 260;
    const paths = buildPath(series, width, height, top, true);
    const last = paths.points[paths.points.length - 1] || [0, height];
    svg.setAttribute("viewBox", `0 0 ${width} 300`);
    svg.innerHTML = `
      <defs>
        <linearGradient id="raidLineGradient" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stop-color="var(--gold-2)" />
          <stop offset="52%" stop-color="var(--gold-3)" />
          <stop offset="100%" stop-color="var(--gold)" />
        </linearGradient>
        <linearGradient id="raidAreaGradient" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stop-color="var(--gold)" stop-opacity=".34" />
          <stop offset="100%" stop-color="var(--gold)" stop-opacity="0" />
        </linearGradient>
      </defs>
      <path class="chart-area" d="${paths.area}" />
      <path class="chart-line" d="${paths.line}" />
      <circle class="chart-pulse" cx="${last[0].toFixed(1)}" cy="${last[1].toFixed(1)}" r="13" />
      <circle class="chart-point hot" cx="${last[0].toFixed(1)}" cy="${last[1].toFixed(1)}" r="8" />
    `;
  };

  const profileIcon = (name) => {
    if (name === "reset") {
      return `<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M20 12a8 8 0 1 1-2.34-5.66" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><path d="M20 4v6h-6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
    }
    return `<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z" stroke="currentColor" stroke-width="1.8"/><path d="M19.4 15a1.8 1.8 0 0 0 .36 1.98l.04.04a2.1 2.1 0 0 1-2.97 2.97l-.04-.04a1.8 1.8 0 0 0-1.98-.36 1.8 1.8 0 0 0-1.1 1.66V21a2.1 2.1 0 0 1-4.2 0v-.06a1.8 1.8 0 0 0-1.18-1.66 1.8 1.8 0 0 0-1.98.36l-.04.04a2.1 2.1 0 1 1-2.97-2.97l.04-.04a1.8 1.8 0 0 0 .36-1.98 1.8 1.8 0 0 0-1.66-1.1H3a2.1 2.1 0 0 1 0-4.2h.06a1.8 1.8 0 0 0 1.66-1.18 1.8 1.8 0 0 0-.36-1.98l-.04-.04a2.1 2.1 0 1 1 2.97-2.97l.04.04a1.8 1.8 0 0 0 1.98.36h.08A1.8 1.8 0 0 0 10.5 3V3a2.1 2.1 0 0 1 4.2 0v.06a1.8 1.8 0 0 0 1.1 1.66 1.8 1.8 0 0 0 1.98-.36l.04-.04a2.1 2.1 0 1 1 2.97 2.97l-.04.04a1.8 1.8 0 0 0-.36 1.98v.08A1.8 1.8 0 0 0 21 10.5h.06a2.1 2.1 0 0 1 0 4.2H21a1.8 1.8 0 0 0-1.6.3Z" stroke="currentColor" stroke-width="1.35" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
  };

  const renderProfiles = (data) => {
    const grid = first(".profile-grid");
    if (!grid) return;
    if (!data.profiles || !data.profiles.length) {
      grid.innerHTML = `<div class="empty-state">No raid profiles configured yet.</div>`;
      return;
    }
    const lightweightProfiles = document.body.classList.contains("performance-mode");
    grid.innerHTML = data.profiles.map((profile) => {
      const statusClass = profile.statusClass || "healthy";
      const dotClass = profile.dotVariant || "";
      const actionButtons = statusClass === "failed"
        ? `<button class="icon-button" data-reset-profile="${html(profile.directory)}" aria-label="Restart">${profileIcon("reset")}</button>`
        : `<button class="icon-button" data-config-profile="${html(profile.directory)}" aria-label="Settings">${profileIcon("settings")}</button>`;
      const chips = (profile.chips || []).map((chip) => `<span class="chip ${html(chip.tone || "")}">${html(chip.label)}</span>`).join("");
      const warmup = profile.warmup ? `
        <div class="warm-progress">
          <div class="progress-meta"><span>Warmup progress</span><span>${html(profile.warmupProgress)}%</span></div>
          <div class="progress-bar"><div class="progress-fill" style="width:${Number(profile.warmupProgress || 0)}%"></div></div>
        </div>` : "";
      const feedback = profile.error || profile.raidNowFeedback || "";
      const error = feedback ? `<div class="profile-error">${html(feedback)}</div>` : "";
      const preview = lightweightProfiles
        ? ""
        : `<div class="profile-preview"><span class="preview-line one"></span><span class="preview-line two"></span></div>`;
      return `
        <article class="profile-card ${html(statusClass)}" data-profile="${html(profile.directory)}">
          <div class="profile-top">
            <div class="profile-name"><span class="profile-dot ${html(dotClass)}"></span>${html(profile.label)}</div>
            ${actionButtons}
          </div>
          ${preview}
          <div class="action-chips">${chips}</div>
          ${warmup}
          ${error}
          <button class="lux-button profile-raid-now" data-raid-profile="${html(profile.directory)}" ${profile.canRaidNow ? "" : "disabled"}>${html(profile.raidNowText || "Raid NOW!")}</button>
        </article>`;
    }).join("");
    all("[data-config-profile]").forEach((button) => {
      button.addEventListener("click", (event) => {
        event.stopPropagation();
        call("configureProfile", button.dataset.configProfile);
      });
    });
    all("[data-reset-profile]").forEach((button) => {
      button.addEventListener("click", (event) => {
        event.stopPropagation();
        call("resetProfile", button.dataset.resetProfile);
      });
    });
    all("[data-raid-profile]").forEach((button) => {
      button.addEventListener("click", (event) => {
        event.stopPropagation();
        call("raidNowForProfile", button.dataset.raidProfile);
      });
    });
  };

  const renderRestartControl = (data) => {
    const control = first(".restart-control");
    if (!control) return;
    const button = control.querySelector(".lux-button");
    const checkbox = control.querySelector("input");
    if (button && !button.dataset.wiredRestart) {
      button.dataset.wiredRestart = "true";
      button.addEventListener("click", () => call("resetAllProfiles"));
    }
    if (checkbox) {
      checkbox.checked = Boolean(data.raidOnRestart);
      if (!checkbox.dataset.wiredRestartRaid) {
        checkbox.dataset.wiredRestartRaid = "true";
        checkbox.addEventListener("change", () => call("setRaidOnRestart", checkbox.checked));
      }
    }
  };

  const renderActivity = (data) => {
    const feed = first(".activity-feed");
    if (!feed) return;
    const entries = data.activity || [];
    if (!entries.length) {
      feed.innerHTML = `<div class="empty-state">No recent raid activity yet.</div>`;
      return;
    }
    feed.innerHTML = entries.map((entry) => `
      <div class="activity-row">
        <div class="activity-profile"><span class="activity-status-dot ${html(entry.tone || "")}"></span>${html(entry.profile || "System")}</div>
        <div class="activity-main"><strong>${html(entry.title)}</strong><span>${html(entry.detail || "")}</span></div>
        <div class="activity-time">${html(entry.time)}</div>
      </div>
    `).join("");
  };

  const formatPath = (value) => value ? String(value) : "No template captured";
  const renderCapturePreview = (template, label) => {
    const src = template?.imageSrc || "";
    if (src) {
      return `<div class="capture-preview has-image"><img src="${html(src)}" alt="${html(label)} preview"></div>`;
    }
    return `<div class="capture-preview"><span class="capture-empty">${template?.saved ? "Preview unavailable" : "No capture"}</span></div>`;
  };

  const renderSettings = (data) => {
    const page = first('[data-page="settings"]');
    if (!page) return;
    const settings = data.settings || {};
    const pageGrid = page.querySelector(".page-grid");
    if (pageGrid) pageGrid.classList.add("runtime-wide");
    page.querySelector(".page-grid > aside.preview-panel")?.remove();
    page.querySelector(".page-hero p")?.remove();
    page.querySelector(".page-hero .lux-button")?.remove();
    const grid = page.querySelector(".settings-grid");
    if (!grid) return;
    const chats = settings.allowedChats || [];
    const senders = settings.allowedSenders || [];
    const profiles = settings.raidProfiles || [];
    grid.innerHTML = `
      <article class="preview-panel">
        <div class="panel-title-row">
          <div><div class="eyebrow">Session</div><h2 class="panel-title">Telegram Access</h2></div>
          <span class="toggle-pill">${html(settings.connection || "Unknown")}</span>
        </div>
        <p class="section-copy">Session health and global pause hotkey.</p>
        <div class="field-stack">
          <div class="field-row"><div class="field-label">Status</div><div class="fake-input">${html(settings.sessionStatus || "unknown")}</div></div>
          <div class="field-row"><div class="field-label">Pause Hotkey</div><div class="fake-input">${html(settings.pauseHotkey || "Not set")}</div></div>
          <div class="field-row"><div class="field-label">Action</div><button class="lux-button" data-web-action="reauthorize">Reauthorize</button></div>
        </div>
      </article>
      <article class="preview-panel">
        <div class="panel-title-row">
          <div><div class="eyebrow">Telegram</div><h2 class="panel-title">API Credentials</h2></div>
          <span class="toggle-pill">Advanced</span>
        </div>
        <p class="section-copy">Values are displayed from the saved desktop configuration.</p>
        <div class="field-stack">
          <div class="field-row"><div class="field-label">API ID</div><div class="fake-input">${html(settings.apiId || "")}</div></div>
          <div class="field-row"><div class="field-label">API Hash</div><div class="fake-input">${html(settings.apiHashMasked || "")}</div></div>
        </div>
      </article>
      <article class="preview-panel">
        <div class="panel-title-row">
          <div><div class="eyebrow">Routing</div><h2 class="panel-title">Allowed Sources</h2></div>
          <span class="toggle-pill">Required</span>
        </div>
        <p class="section-copy">Allowed chats and senders used for recent-link lookup and automatic raids.</p>
        <div class="field-stack">
          <div class="field-row"><div class="field-label">Allowed chats</div><div class="fake-list">${chats.length ? chats.map((chat) => `<div class="list-item"><strong>${html(chat.label)}</strong><span>allowed chat</span></div>`).join("") : `<div class="list-item"><strong>No chats</strong><span>Add one in setup</span></div>`}</div></div>
          <div class="field-row"><div class="field-label">Allowed senders</div><div class="fake-list">${senders.length ? senders.map((sender) => `<div class="list-item"><strong>${html(sender)}</strong><span>allowed</span></div>`).join("") : `<div class="list-item"><strong>No senders</strong><span>Scan recent messages</span></div>`}</div></div>
        </div>
        <div class="form-actions">
          <button class="lux-button" data-web-action="refresh-chats">Refresh chats</button>
          <button class="lux-button" data-web-action="scan-senders">Scan senders</button>
        </div>
      </article>
      <article class="preview-panel">
        <div class="panel-title-row">
          <div><div class="eyebrow">Routing</div><h2 class="panel-title">Raid Profiles</h2></div>
          <span class="toggle-pill">${profiles.length} profiles</span>
        </div>
        <p class="section-copy">Ordered profile list. Move controls operate on the selected row below.</p>
        <div class="fake-list">${profiles.map((profile, index) => `<button class="list-item" type="button" data-select-settings-profile="${html(profile.directory)}"><strong>${html(profile.label)}</strong><span>${html(profile.status)}${index === 0 ? " · primary" : ""}</span></button>`).join("") || `<div class="list-item"><strong>No profiles</strong><span>Refresh Chrome profiles</span></div>`}</div>
        <div class="form-actions">
          <button class="lux-button" data-web-action="add-profile">Add profile</button>
          <button class="lux-button" data-web-action="move-profile-up">Move up</button>
          <button class="lux-button" data-web-action="move-profile-down">Move down</button>
          <button class="lux-button" data-web-action="remove-profile">Remove profile</button>
        </div>
      </article>
    `;
    let selectedProfile = profiles[0]?.directory || "";
    all("[data-select-settings-profile]").forEach((button) => {
      button.addEventListener("click", () => {
        selectedProfile = button.dataset.selectSettingsProfile || "";
        all("[data-select-settings-profile]").forEach((item) => item.classList.remove("active"));
        button.classList.add("active");
      });
    });
    const firstProfileButton = first("[data-select-settings-profile]");
    if (firstProfileButton) firstProfileButton.classList.add("active");
    const actions = {
      "reauthorize": () => call("reauthorize"),
      "refresh-chats": () => call("refreshChats"),
      "scan-senders": () => call("scanSenders"),
      "add-profile": () => call("addProfile"),
      "move-profile-up": () => call("moveProfile", selectedProfile, "up"),
      "move-profile-down": () => call("moveProfile", selectedProfile, "down"),
      "remove-profile": () => call("removeProfile", selectedProfile),
    };
    all("[data-web-action]").forEach((button) => {
      button.addEventListener("click", () => actions[button.dataset.webAction]?.());
    });
  };

  const renderBotActions = (data) => {
    const page = first('[data-page="bot-actions"]');
    if (!page) return;
    const bot = data.botActions || {};
    const pageGrid = page.querySelector(".page-grid");
    if (pageGrid) pageGrid.classList.add("runtime-wide");
    page.querySelector(".page-grid > aside.preview-panel")?.remove();
    page.querySelector(".page-hero .lux-button")?.remove();
    const grid = page.querySelector(".bot-actions-grid");
    if (!grid) return;
    const slots = bot.slots || [];
    const pageReadyTimeout = Math.round(Number(bot.pageReadyTimeoutSeconds || 12));
    grid.innerHTML = `
      <article class="preview-panel">
        <div class="panel-title-row">
          <div><div class="eyebrow">Page Templates</div></div>
        </div>
        <div class="capture-grid">
          ${["page_ready", "page_exit"].map((key) => {
            const template = bot.pageTemplates?.[key] || {};
            return `<div class="capture-card">
              <div class="slot-header"><strong>${html(template.label)}</strong><span class="toggle-pill">${template.saved ? "Saved" : "Missing"}</span></div>
              ${renderCapturePreview(template, template.label || key)}
              <span class="template-path">${html(formatPath(template.path))}</span>
              <div class="mini-button-row">
                <button class="tiny-button" data-page-template-capture="${html(key)}">Capture</button>
                <button class="tiny-button" data-page-template-test="${html(key)}">Test</button>
              </div>
            </div>`;
          }).join("")}
        </div>
        <div class="page-ready-timeout-card">
          <div>
            <strong>Page Ready timeout</strong>
            <span>Seconds to wait before CLDF troubleshooting starts.</span>
          </div>
          <input class="runtime-field-input" type="number" min="1" max="300" step="1" value="${pageReadyTimeout}" data-page-ready-timeout>
        </div>
      </article>
      <article class="preview-panel">
        <div class="panel-title-row">
          <div><div class="eyebrow">Presets</div></div>
        </div>
        <p class="section-copy">Slot 1 preset management and finish image capture.</p>
        <div class="preset-summary">
          <div class="preset-count-card"><strong>${Number(bot.presetCount || 0)}</strong><span>Reply presets saved</span></div>
          <div>
            <div class="slot-header"><strong>Finish image</strong><span class="toggle-pill">${bot.finishTemplateSaved ? "Saved" : "Missing"}</span></div>
            ${renderCapturePreview({ imageSrc: bot.finishTemplateImageSrc, saved: bot.finishTemplateSaved }, "Finish image")}
            <span class="template-path">${html(formatPath(bot.finishTemplatePath))}</span>
          </div>
        </div>
        <div class="form-actions"><button class="lux-button" data-slot-presets="0">Open presets</button><button class="lux-button" data-slot-finish-capture="0">Capture finish image</button></div>
      </article>
      <article class="preview-panel" style="grid-column: 1 / -1;">
        <div class="panel-title-row">
          <div><div class="eyebrow">Action Slots</div></div>
        </div>
        <div class="slot-grid">
          ${slots.map((slot, index) => `<div class="slot-card">
            <div class="slot-header"><div class="slot-title">Slot ${index + 1} · ${html(slot.name)}</div></div>
            ${renderCapturePreview(slot, `Slot ${index + 1} ${slot.name}`)}
            <span class="template-path">${html(formatPath(slot.path))}</span>
            <div class="slot-meta"><div class="meta-box"><strong>${html(slot.delay)}</strong><span>Delay</span></div><div class="meta-box"><strong>${slot.saved ? "Saved" : "Missing"}</strong><span>Capture</span></div></div>
            <div class="mini-button-row">
              <button class="tiny-button" data-slot-capture="${index}">Capture</button>
              <button class="tiny-button" data-slot-test="${index}">Test</button>
            </div>
          </div>`).join("")}
        </div>
      </article>
    `;
    all("[data-page-template-capture]").forEach((button) => button.addEventListener("click", () => call("capturePageTemplate", button.dataset.pageTemplateCapture)));
    all("[data-page-template-test]").forEach((button) => button.addEventListener("click", () => call("testPageTemplate", button.dataset.pageTemplateTest)));
    all("[data-page-ready-timeout]").forEach((input) => {
      input.addEventListener("change", () => {
        const parsed = Number(input.value || 12);
        const value = Number.isFinite(parsed) ? Math.max(1, Math.min(300, Math.round(parsed))) : 12;
        input.value = String(value);
        call("setPageReadyTimeout", value);
      });
    });
    all("[data-slot-capture]").forEach((button) => button.addEventListener("click", () => call("captureSlot", Number(button.dataset.slotCapture))));
    all("[data-slot-test]").forEach((button) => button.addEventListener("click", () => call("testSlot", Number(button.dataset.slotTest))));
    all("[data-slot-presets]").forEach((button) => button.addEventListener("click", () => call("openSlotPresets", Number(button.dataset.slotPresets))));
    all("[data-slot-finish-capture]").forEach((button) => button.addEventListener("click", () => call("captureSlotFinish", Number(button.dataset.slotFinishCapture))));
  };

  const renderTroubleshoot = (data) => {
    const page = first('[data-page="troubleshoot"]');
    if (!page) return;
    const trouble = data.troubleshoot || {};
    const pageGrid = page.querySelector(".page-grid");
    if (pageGrid) pageGrid.classList.add("runtime-wide");
    page.querySelector(".page-grid > aside.preview-panel")?.remove();
    const heroButton = page.querySelector(".page-hero .lux-button");
    if (heroButton && !heroButton.dataset.wiredCldfTest) {
      heroButton.dataset.wiredCldfTest = "true";
      heroButton.addEventListener("click", () => call("testTroubleshoot", "cldf", 0));
    }
    const content = page.querySelector(".troubleshoot-content");
    if (!content) return;
    const sections = [
      { key: "cldf", title: "CLDF Capture Path", steps: trouble.cldf || [] },
      { key: "black_box", title: "Black Box Escape", steps: trouble.black_box || [] },
    ];
    content.innerHTML = sections.map((section) => `
      <article class="preview-panel trouble-section-panel">
        <div class="panel-title-row"><div><div class="eyebrow">${html(section.title)}</div></div></div>
        <div class="trouble-path ${section.key === "black_box" ? "single" : ""}">
          ${section.steps.map((step, index) => `
            <div class="trouble-card">
              <div class="trouble-header"><div class="trouble-title">Capture</div><div class="trouble-number">${section.key === "cldf" ? index + 1 : "ESC"}</div></div>
              ${renderCapturePreview(step, step.label || `${section.title} ${index + 1}`)}
              <span class="template-path">${html(formatPath(step.path))}</span>
              <div class="mini-button-row"><button class="tiny-button" data-trouble-group="${html(section.key)}" data-trouble-capture="${index}">Capture</button><button class="tiny-button" data-trouble-group="${html(section.key)}" data-trouble-test="${index}">Test</button></div>
            </div>
          `).join("")}
        </div>
      </article>
    `).join("");
    all("[data-trouble-capture]").forEach((button) => button.addEventListener("click", () => call("captureTroubleshoot", button.dataset.troubleGroup || "cldf", Number(button.dataset.troubleCapture))));
    all("[data-trouble-test]").forEach((button) => button.addEventListener("click", () => call("testTroubleshoot", button.dataset.troubleGroup || "cldf", Number(button.dataset.troubleTest))));
  };

  window.raidbotSetDashboardState = (payload) => {
    const data = typeof payload === "string" ? JSON.parse(payload) : payload;
    state.latest = data;
    applyPerformanceMode(Boolean(data.performanceMode));
    renderTopbar(data);
    renderCommand(data);
    renderChart(data);
    renderProfiles(data);
    renderRestartControl(data);
    renderActivity(data);
    renderSettings(data);
    renderBotActions(data);
    renderTroubleshoot(data);
    renderSidebarVersion(data);
  };

  document.addEventListener("DOMContentLoaded", () => {
    wireButtons();
    if (window.qt && window.QWebChannel) {
      new QWebChannel(qt.webChannelTransport, (channel) => {
        state.bridge = channel.objects.dashboardBridge;
        call("dashboardReady");
      });
    }
    if (state.latest) window.raidbotSetDashboardState(state.latest);
  });
})();
</script>
"""


def default_dashboard_preview_path() -> Path:
    bundled_root = Path(getattr(sys, "_MEIPASS", "") or "")
    candidates: list[Path] = []
    if bundled_root:
        candidates.append(
            bundled_root / "docs" / "ui-preview" / "dashboard-refresh-preview.html"
        )
    candidates.append(
        Path(__file__).resolve().parents[2]
        / "docs"
        / "ui-preview"
        / "dashboard-refresh-preview.html"
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[-1]


class DashboardBridge(QObject):
    def __init__(
        self,
        *,
        on_ready: Callable[[], None],
        on_start: Callable[[], None],
        on_stop: Callable[[], None],
        on_toggle_pause: Callable[[], None],
        on_raid_now: Callable[[], None],
        on_raid_now_for_profile: Callable[[str], None],
        on_reset_profile: Callable[[str], None],
        on_configure_profile: Callable[[str], None],
        on_reset_all_profiles: Callable[[], None],
        on_set_raid_on_restart: Callable[[bool], None],
        on_set_performance_mode: Callable[[bool], None],
        on_set_page_ready_timeout: Callable[[float], None],
        on_reauthorize: Callable[[], None],
        on_refresh_chats: Callable[[], None],
        on_scan_senders: Callable[[], None],
        on_add_profile: Callable[[], None],
        on_move_profile: Callable[[str, str], None],
        on_remove_profile: Callable[[str], None],
        on_capture_page_template: Callable[[str], None],
        on_test_page_template: Callable[[str], None],
        on_capture_slot: Callable[[int], None],
        on_test_slot: Callable[[int], None],
        on_open_slot_presets: Callable[[int], None],
        on_capture_slot_finish: Callable[[int], None],
        on_test_enabled_slots: Callable[[], None],
        on_capture_troubleshoot: Callable[[str, int], None],
        on_test_troubleshoot: Callable[[str, int], None],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._on_ready = on_ready
        self._on_start = on_start
        self._on_stop = on_stop
        self._on_toggle_pause = on_toggle_pause
        self._on_raid_now = on_raid_now
        self._on_raid_now_for_profile = on_raid_now_for_profile
        self._on_reset_profile = on_reset_profile
        self._on_configure_profile = on_configure_profile
        self._on_reset_all_profiles = on_reset_all_profiles
        self._on_set_raid_on_restart = on_set_raid_on_restart
        self._on_set_performance_mode = on_set_performance_mode
        self._on_set_page_ready_timeout = on_set_page_ready_timeout
        self._on_reauthorize = on_reauthorize
        self._on_refresh_chats = on_refresh_chats
        self._on_scan_senders = on_scan_senders
        self._on_add_profile = on_add_profile
        self._on_move_profile = on_move_profile
        self._on_remove_profile = on_remove_profile
        self._on_capture_page_template = on_capture_page_template
        self._on_test_page_template = on_test_page_template
        self._on_capture_slot = on_capture_slot
        self._on_test_slot = on_test_slot
        self._on_open_slot_presets = on_open_slot_presets
        self._on_capture_slot_finish = on_capture_slot_finish
        self._on_test_enabled_slots = on_test_enabled_slots
        self._on_capture_troubleshoot = on_capture_troubleshoot
        self._on_test_troubleshoot = on_test_troubleshoot

    @Slot()
    def dashboardReady(self) -> None:
        self._on_ready()

    @Slot()
    def startBot(self) -> None:
        self._on_start()

    @Slot()
    def stopBot(self) -> None:
        self._on_stop()

    @Slot()
    def togglePauseResume(self) -> None:
        self._on_toggle_pause()

    @Slot()
    def raidNow(self) -> None:
        self._on_raid_now()

    @Slot(str)
    def raidNowForProfile(self, profile_directory: str) -> None:
        self._on_raid_now_for_profile(str(profile_directory))

    @Slot(str)
    def resetProfile(self, profile_directory: str) -> None:
        self._on_reset_profile(str(profile_directory))

    @Slot(str)
    def configureProfile(self, profile_directory: str) -> None:
        self._on_configure_profile(str(profile_directory))

    @Slot()
    def resetAllProfiles(self) -> None:
        self._on_reset_all_profiles()

    @Slot(bool)
    def setRaidOnRestart(self, enabled: bool) -> None:
        self._on_set_raid_on_restart(bool(enabled))

    @Slot(bool)
    def setPerformanceMode(self, enabled: bool) -> None:
        self._on_set_performance_mode(bool(enabled))

    @Slot(float)
    def setPageReadyTimeout(self, seconds: float) -> None:
        self._on_set_page_ready_timeout(float(seconds))

    @Slot()
    def reauthorize(self) -> None:
        self._on_reauthorize()

    @Slot()
    def refreshChats(self) -> None:
        self._on_refresh_chats()

    @Slot()
    def scanSenders(self) -> None:
        self._on_scan_senders()

    @Slot()
    def addProfile(self) -> None:
        self._on_add_profile()

    @Slot(str, str)
    def moveProfile(self, profile_directory: str, direction: str) -> None:
        self._on_move_profile(str(profile_directory), str(direction))

    @Slot(str)
    def removeProfile(self, profile_directory: str) -> None:
        self._on_remove_profile(str(profile_directory))

    @Slot(str)
    def capturePageTemplate(self, template_key: str) -> None:
        self._on_capture_page_template(str(template_key))

    @Slot(str)
    def testPageTemplate(self, template_key: str) -> None:
        self._on_test_page_template(str(template_key))

    @Slot(int)
    def captureSlot(self, slot_index: int) -> None:
        self._on_capture_slot(int(slot_index))

    @Slot(int)
    def testSlot(self, slot_index: int) -> None:
        self._on_test_slot(int(slot_index))

    @Slot(int)
    def openSlotPresets(self, slot_index: int) -> None:
        self._on_open_slot_presets(int(slot_index))

    @Slot(int)
    def captureSlotFinish(self, slot_index: int) -> None:
        self._on_capture_slot_finish(int(slot_index))

    @Slot()
    def testEnabledSlots(self) -> None:
        self._on_test_enabled_slots()

    @Slot(str, int)
    def captureTroubleshoot(self, group_key: str, item_index: int) -> None:
        self._on_capture_troubleshoot(str(group_key), int(item_index))

    @Slot(str, int)
    def testTroubleshoot(self, group_key: str, item_index: int) -> None:
        self._on_test_troubleshoot(str(group_key), int(item_index))


class DashboardWebView(QWidget):
    def __init__(
        self,
        *,
        on_start: Callable[[], None],
        on_stop: Callable[[], None],
        on_toggle_pause: Callable[[], None],
        on_raid_now: Callable[[], None],
        on_raid_now_for_profile: Callable[[str], None],
        on_reset_profile: Callable[[str], None],
        on_configure_profile: Callable[[str], None],
        on_reset_all_profiles: Callable[[], None],
        on_set_raid_on_restart: Callable[[bool], None],
        on_set_performance_mode: Callable[[bool], None],
        on_set_page_ready_timeout: Callable[[float], None],
        on_reauthorize: Callable[[], None],
        on_refresh_chats: Callable[[], None],
        on_scan_senders: Callable[[], None],
        on_add_profile: Callable[[], None],
        on_move_profile: Callable[[str, str], None],
        on_remove_profile: Callable[[str], None],
        on_capture_page_template: Callable[[str], None],
        on_test_page_template: Callable[[str], None],
        on_capture_slot: Callable[[int], None],
        on_test_slot: Callable[[int], None],
        on_open_slot_presets: Callable[[int], None],
        on_capture_slot_finish: Callable[[int], None],
        on_test_enabled_slots: Callable[[], None],
        on_capture_troubleshoot: Callable[[str, int], None],
        on_test_troubleshoot: Callable[[str, int], None],
        html_path: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._loaded = False
        self._pending_state: dict[str, Any] | None = None
        self._html_path = html_path or default_dashboard_preview_path()
        self._offscreen_fallback = (
            os.environ.get("QT_QPA_PLATFORM", "").strip().lower() == "offscreen"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        if self._offscreen_fallback:
            self.view = QLabel("Dashboard Web Preview")
            self.view.setObjectName("dashboardWebView")
            self.view.setProperty("offscreenFallback", True)
            layout.addWidget(self.view)
            self._loaded = True
            return

        self.view = QWebEngineView(self)
        self.view.setObjectName("dashboardWebView")
        self.view.loadFinished.connect(self._handle_load_finished)
        self.bridge = DashboardBridge(
            on_ready=self._flush_pending_state,
            on_start=on_start,
            on_stop=on_stop,
            on_toggle_pause=on_toggle_pause,
            on_raid_now=on_raid_now,
            on_raid_now_for_profile=on_raid_now_for_profile,
            on_reset_profile=on_reset_profile,
            on_configure_profile=on_configure_profile,
            on_reset_all_profiles=on_reset_all_profiles,
            on_set_raid_on_restart=on_set_raid_on_restart,
            on_set_performance_mode=on_set_performance_mode,
            on_set_page_ready_timeout=on_set_page_ready_timeout,
            on_reauthorize=on_reauthorize,
            on_refresh_chats=on_refresh_chats,
            on_scan_senders=on_scan_senders,
            on_add_profile=on_add_profile,
            on_move_profile=on_move_profile,
            on_remove_profile=on_remove_profile,
            on_capture_page_template=on_capture_page_template,
            on_test_page_template=on_test_page_template,
            on_capture_slot=on_capture_slot,
            on_test_slot=on_test_slot,
            on_open_slot_presets=on_open_slot_presets,
            on_capture_slot_finish=on_capture_slot_finish,
            on_test_enabled_slots=on_test_enabled_slots,
            on_capture_troubleshoot=on_capture_troubleshoot,
            on_test_troubleshoot=on_test_troubleshoot,
            parent=self,
        )
        self.channel = QWebChannel(self.view.page())
        self.channel.registerObject("dashboardBridge", self.bridge)
        self.view.page().setWebChannel(self.channel)
        layout.addWidget(self.view)
        self.reload()

    def reload(self) -> None:
        if self._offscreen_fallback:
            self._loaded = True
            return
        html = self._load_html()
        base_url = QUrl.fromLocalFile(str(self._html_path.parent) + "/")
        self._loaded = False
        self.view.setHtml(html, base_url)

    def set_state(self, state: dict[str, Any]) -> None:
        self._pending_state = state
        if self._loaded:
            self._flush_pending_state()

    def _handle_load_finished(self, ok: bool) -> None:
        self._loaded = bool(ok)
        if self._loaded:
            self._flush_pending_state()

    def _flush_pending_state(self) -> None:
        if not self._loaded or self._pending_state is None:
            return
        if self._offscreen_fallback:
            return
        payload = json.dumps(self._pending_state, ensure_ascii=False)
        self.view.page().runJavaScript(
            f"window.raidbotSetDashboardState && window.raidbotSetDashboardState({payload});"
        )

    def _load_html(self) -> str:
        html = self._html_path.read_text(encoding="utf-8")
        html = re.sub(
            r"<title>.*?</title>",
            "<title>L8N Raid Bot Dashboard</title>",
            html,
            count=1,
            flags=re.S,
        )
        html = html.replace("</head>", f"{_DASHBOARD_RUNTIME_STYLE}\n</head>", 1)
        html = html.replace("</body>", f"{_DASHBOARD_RUNTIME_SCRIPT}\n</body>", 1)
        return html
