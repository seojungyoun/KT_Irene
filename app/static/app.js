/* KT Irene Studio — app.js (v3) */
'use strict';

// ── 전역 상태 ─────────────────────────────────────────────────────────────
let project = null;
let pollTimer = null;

// ── DOM 참조 ──────────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);

const btnNew      = $('btnNew');
const btnGenAll   = $('btnGenAll');
const btnRender   = $('btnRender');
const btnDownload = $('btnDownload');
const ireneUpload = $('ireneUpload');
const ttsStatus   = $('ttsStatus');

const progressWrap  = $('progressWrap');
const progressFill  = $('progressFill');
const progressLabel = $('progressLabel');
const progressPct   = $('progressPct');

const monitorVideo       = $('monitorVideo');
const monitorPlaceholder = $('monitorPlaceholder');
const timeline           = $('timeline');
const irenePreview       = $('irenePreview');

const projectStatus = $('projectStatus');
const sceneList     = $('sceneList');
const emptyScenes   = $('emptyScenes');
const sceneCount    = $('sceneCount');
const scriptCharCount = $('scriptCharCount');
const recommendedLimit = $('recommendedLimit');

const fScript    = $('fScript');
const fTargetSec = $('fTargetSec');

// ── 유틸 ─────────────────────────────────────────────────────────────────

async function api(url, opts = {}) {
  const res  = await fetch(url, opts);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `${res.status} ${res.statusText}`);
  return body;
}

let toastTimer = null;
function toast(msg, type = 'info') {   // type: info | success | error
  const el = $('toast');
  el.textContent = msg;
  el.className = `toast${type === 'error' ? ' error' : type === 'success' ? ' success' : ''}`;
  el.classList.remove('hidden');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.add('hidden'), 3500);
}

function setButtonsEnabled(hasProject) {
  btnGenAll.disabled = !hasProject;
  btnRender.disabled = !hasProject;
}

const STATUS_MAP = {
  draft:      ['pill-gray',   '초안'],
  generating: ['pill-orange', '생성 중'],
  rendered:   ['pill-green',  '완료'],
  error:      ['pill-red',    '오류'],
};
function statusClass(s) { return (STATUS_MAP[s] || STATUS_MAP.draft)[0]; }
function statusLabel(s) { return (STATUS_MAP[s] || STATUS_MAP.draft)[1]; }
function statusPill(status) {
  return `<span class="status-pill ${statusClass(status)}">${statusLabel(status)}</span>`;
}

// ── 설정 수집 ────────────────────────────────────────────────────────────
function collectPayload() {
  return {
    title:            $('fTitle').value.trim() || '뉴스 브리핑',
    template:         $('fTemplate').value,
    background:       $('fBg').value,
    outfit:           $('fOutfit').value,
    hair:             $('fHair').value,
    logo_position:    $('fLogoPos').value,
    logo_scale:       12,
    subtitle_font:    'Pretendard',
    target_scene_sec: Number(fTargetSec.value),
    script:           fScript.value,
  };
}

function collectSettings() {
  const p = collectPayload();
  const { title, script, target_scene_sec, ...settings } = p;
  return settings;
}

// ── 미리보기 플레이어 ────────────────────────────────────────────────────
function playInMonitor(url) {
  if (!url) return;
  monitorVideo.src = url;
  monitorVideo.classList.remove('hidden');
  monitorPlaceholder.classList.add('hidden');
  monitorVideo.load();
  monitorVideo.play().catch(() => {});
}

// ── 타임라인 렌더 ────────────────────────────────────────────────────────
function renderTimeline(scenes) {
  timeline.innerHTML = '';
  if (!scenes || !scenes.length) return;

  scenes.forEach(s => {
    const clip = document.createElement('div');
    clip.className = `timeline-clip${s.status === 'generated' ? ' generated' : ''}`;
    clip.dataset.sceneId = s.scene_id;

    if (s.last_frame_url) {
      clip.innerHTML = `
        <img class="timeline-thumb" src="${s.last_frame_url}" alt="씬${s.order_index+1}"/>
        <div class="timeline-label">씬 ${s.order_index + 1}</div>`;
    } else {
      clip.innerHTML = `
        <div class="timeline-thumb-placeholder">🎞</div>
        <div class="timeline-label">씬 ${s.order_index + 1}</div>`;
    }

    clip.addEventListener('click', () => {
      document.querySelectorAll('.timeline-clip').forEach(c => c.classList.remove('active'));
      clip.classList.add('active');
      if (s.video_url) playInMonitor(s.video_url);
    });

    timeline.appendChild(clip);
  });
}

// ── 씬 카드 렌더 ─────────────────────────────────────────────────────────
function sceneCard(s) {
  const over    = s.script_text.length > s.recommended_char_limit;
  const isDone  = s.status === 'generated';
  const dur     = s.duration_sec > 0 ? `${s.duration_sec.toFixed(1)}s` : '';

  return `
<div class="scene-card ${s.status}" id="card_${s.scene_id}">
  <div class="scene-head">
    <span class="scene-num">씬 ${s.order_index + 1}</span>
    <span class="scene-char-count ${over ? 'over' : ''}">
      ${s.script_text.length} / ${s.recommended_char_limit}자${over ? ' ⚠' : ''}
    </span>
    ${statusPill(s.status)}
    ${dur ? `<span class="scene-dur">${dur}</span>` : ''}
  </div>

  <div class="scene-body">
    <textarea id="stxt_${s.scene_id}" rows="3">${esc(s.script_text)}</textarea>
  </div>

  <div class="scene-dict-wrap">
    <label>발음 사전 (JSON)
      <input id="dict_${s.scene_id}" placeholder='{"KT":"케이티","5G":"파이브지"}' value='${dictVal(s.pronunciation_dict)}'/>
    </label>
  </div>

  <div class="scene-actions">
    <button class="btn" onclick="doUpdateScene('${s.scene_id}')">대본 저장</button>
    <button class="btn btn-primary" onclick="doGenScene('${s.scene_id}')"
            id="gbtn_${s.scene_id}">씬 생성${isDone ? ' (재생성)' : ''}</button>
    ${isDone ? `
      <button class="btn" onclick="playInMonitor('${s.video_url}')">▶ 미리보기</button>
      <a href="${s.video_url}" target="_blank">영상↗</a>
      <a href="${s.tts_audio_url}" target="_blank">음성↗</a>
      <a href="${s.subtitle_url}" target="_blank">자막↗</a>
    ` : ''}
  </div>
</div>`;
}

function esc(str) {
  return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
            .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

function dictVal(d) {
  if (!d || !Object.keys(d).length) return '';
  return esc(JSON.stringify(d));
}

// ── 프로젝트 렌더 ────────────────────────────────────────────────────────
function renderProject(p) {
  project = p;
  setButtonsEnabled(true);

  // 상태 필
  projectStatus.innerHTML = '';
  projectStatus.className = `status-pill ${statusClass(p.status)}`;
  projectStatus.textContent = statusLabel(p.status);

  // 씬 목록
  if (p.scenes && p.scenes.length) {
    sceneList.innerHTML = p.scenes.map(sceneCard).join('');
    emptyScenes.classList.add('hidden');
    sceneCount.textContent = `총 ${p.scenes.length}개 씬`;
  } else {
    sceneList.innerHTML = '';
    emptyScenes.classList.remove('hidden');
    sceneCount.textContent = '씬 없음';
  }

  renderTimeline(p.scenes);

  // 최종 영상 다운로드 버튼
  if (p.final_video_url) {
    btnDownload.href = p.final_video_url;
    btnDownload.classList.remove('hidden');
    playInMonitor(p.final_video_url);
  }
}

// ── 글자 수 힌트 ──────────────────────────────────────────────────────────
fScript.addEventListener('input', () => {
  scriptCharCount.textContent = `${fScript.value.length}자`;
});

fTargetSec.addEventListener('input', () => {
  const sec = Number(fTargetSec.value);
  const limit = Math.round(sec * 7);
  recommendedLimit.textContent = `${limit}자`;
});
// 초기값 설정
recommendedLimit.textContent = `${Math.round(Number(fTargetSec.value) * 7)}자`;

// ══════════════════════════════════════════════════════════════════════════
// 이벤트 핸들러
// ══════════════════════════════════════════════════════════════════════════

// ── 새 프로젝트 ──────────────────────────────────────────────────────────
btnNew.addEventListener('click', async () => {
  const payload = collectPayload();
  if (!payload.script.trim()) { toast('대본을 입력해 주세요.', 'error'); return; }
  try {
    btnNew.disabled = true;
    const p = await api('/api/projects', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(payload),
    });
    renderProject(p);
    toast(`프로젝트 "${p.title}" 생성 완료 — ${p.scenes.length}개 씬으로 분할`, 'success');
  } catch(e) {
    toast(`생성 실패: ${e.message}`, 'error');
  } finally {
    btnNew.disabled = false;
  }
});

// ── 씬 대본 저장 ─────────────────────────────────────────────────────────
window.doUpdateScene = async (sceneId) => {
  if (!project) return;
  const script = $(`stxt_${sceneId}`).value;
  try {
    const p = await api(`/api/projects/${project.project_id}/scenes/${sceneId}`, {
      method: 'PATCH',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({script}),
    });
    renderProject(p);
    toast('대본이 저장되었습니다.', 'success');
  } catch(e) {
    toast(`저장 실패: ${e.message}`, 'error');
  }
};

// ── 씬 개별 생성 ─────────────────────────────────────────────────────────
window.doGenScene = async (sceneId) => {
  if (!project) return;

  let pronunciation_dict = {};
  const raw = $(`dict_${sceneId}`).value.trim();
  if (raw) {
    try { pronunciation_dict = JSON.parse(raw); }
    catch { toast('발음 사전 JSON 형식 오류', 'error'); return; }
  }

  const btn = $(`gbtn_${sceneId}`);
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> 생성 중…';

  try {
    const p = await api(`/api/projects/${project.project_id}/scenes/${sceneId}/generate`, {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({pronunciation_dict}),
    });
    renderProject(p);
    toast('씬 생성 완료', 'success');
  } catch(e) {
    toast(`씬 생성 실패: ${e.message}`, 'error');
    btn.disabled = false;
    btn.innerHTML = '씬 생성';
  }
};

// ── 전체 생성 (비동기 폴링) ────────────────────────────────────────────────
btnGenAll.addEventListener('click', async () => {
  if (!project) return;

  // 먼저 설정 저장
  try {
    await api(`/api/projects/${project.project_id}/settings`, {
      method: 'PATCH',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(collectSettings()),
    });
  } catch(_) {}

  try {
    await api(`/api/projects/${project.project_id}/generate-all`, {method:'POST'});
  } catch(e) {
    if (!e.message.includes('이미 생성')) {
      toast(`시작 실패: ${e.message}`, 'error');
      return;
    }
  }

  toast('전체 씬 생성을 시작했습니다…', 'info');
  startPolling(project.project_id);
});

// ── 최종 렌더 ────────────────────────────────────────────────────────────
btnRender.addEventListener('click', async () => {
  if (!project) return;
  btnRender.disabled = true;
  btnRender.innerHTML = '<span class="spinner"></span> 렌더 중…';
  try {
    await api(`/api/projects/${project.project_id}/settings`, {
      method: 'PATCH',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(collectSettings()),
    });
    const p = await api(`/api/projects/${project.project_id}/render-final`, {method:'POST'});
    renderProject(p);
    toast('최종 렌더 완료!', 'success');
  } catch(e) {
    toast(`렌더 실패: ${e.message}`, 'error');
  } finally {
    btnRender.disabled = false;
    btnRender.innerHTML = '⬇ 최종 렌더';
  }
});

// ── 진행 폴링 ────────────────────────────────────────────────────────────
function startPolling(projectId) {
  clearInterval(pollTimer);
  showProgress(0, '전체 생성 준비 중…');

  pollTimer = setInterval(async () => {
    try {
      const data = await api(`/api/projects/${projectId}/progress`);
      const pct = data.percent || 0;
      const label = data.status === 'rendered'
        ? '완료!'
        : `씬 생성 중… (${data.done}/${data.total})`;

      updateProgress(pct, label);

      if (data.error) {
        stopPolling();
        hideProgress();
        toast(`생성 오류: ${data.error}`, 'error');
        return;
      }

      if (data.status === 'rendered') {
        stopPolling();
        updateProgress(100, '완료!');
        setTimeout(hideProgress, 2000);

        const p = await api(`/api/projects/${projectId}`);
        renderProject(p);
        toast('전체 생성 및 렌더 완료!', 'success');
      }
    } catch(_) {}
  }, 2000);
}

function stopPolling()  { clearInterval(pollTimer); pollTimer = null; }

function showProgress(pct, label) {
  progressWrap.classList.remove('hidden');
  updateProgress(pct, label);
}

function updateProgress(pct, label) {
  progressFill.style.width  = `${pct}%`;
  progressPct.textContent   = `${pct}%`;
  progressLabel.textContent = label;
}

function hideProgress() {
  progressWrap.classList.add('hidden');
}

// ── 아이린 이미지 업로드 ────────────────────────────────────────────────
ireneUpload.addEventListener('change', async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const fd = new FormData();
  fd.append('file', file);
  try {
    await api('/api/irene/upload-reference', {method:'POST', body: fd});
    irenePreview.src = `/api/irene/reference?t=${Date.now()}`;
    irenePreview.style.display = '';
    $('ireneFallback').style.display = 'none';
    toast('아이린 레퍼런스 이미지가 업데이트되었습니다.', 'success');
  } catch(e) {
    toast(`업로드 실패: ${e.message}`, 'error');
  }
});

// ── TTS / AI 영상 상태 확인 ──────────────────────────────────────────────
async function checkTtsStatus() {
  try {
    await api('/health');
    ttsStatus.textContent = '서버 정상';
    ttsStatus.className = 'status-pill pill-green';
  } catch {
    ttsStatus.textContent = '서버 오프라인';
    ttsStatus.className = 'status-pill pill-red';
  }
}

async function checkAiVideoStatus() {
  const el = $('aiVideoStatus');
  if (!el) return;
  try {
    const s = await api('/api/ai-video/status');
    if (s.ai_enabled) {
      const icon = s.lip_sync ? '🎙' : '🎬';
      el.textContent = `${icon} ${s.label}`;
      el.className = 'status-pill pill-green';
      el.title = s.lip_sync
        ? '실제 립싱크: TTS 오디오에 맞춰 입 모양이 생성됩니다'
        : '동작 영상: 말하는 동작 생성 후 TTS 오디오 overlay (립싱크 아님)';
    } else {
      el.textContent = '🖼 정적 프레임';
      el.className = 'status-pill pill-gray';
      el.title = 'AI 영상 API 키 미설정\nKLING_ACCESS_KEY+KLING_SECRET_KEY (립싱크)\nGOOGLE_API_KEY (Veo 3)\nMINIMAX_API_KEY+MINIMAX_GROUP_ID (Hailuo)';
    }
  } catch {
    el.textContent = 'AI 영상 확인 불가';
    el.className = 'status-pill pill-red';
  }
}

checkTtsStatus();
checkAiVideoStatus();

// ══════════════════════════════════════════════════════════════════════════
// 에셋 관리
// ══════════════════════════════════════════════════════════════════════════

// ── 탭 전환 ──────────────────────────────────────────────────────────────
document.querySelectorAll('.asset-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.asset-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.asset-panel').forEach(p => p.classList.remove('active'));
    tab.classList.add('active');
    $(`panel${cap(tab.dataset.tab)}`).classList.add('active');
  });
});

function cap(s) { return s.charAt(0).toUpperCase() + s.slice(1); }

// ── 업로드 공통 ───────────────────────────────────────────────────────────
async function uploadAsset(inputEl, endpoint, statusEl, previewImg, noEl, bust = true) {
  const file = inputEl.files[0];
  if (!file) return;
  inputEl.value = '';

  statusEl.textContent = '업로드 중…';
  statusEl.className = 'upload-status';
  statusEl.classList.remove('hidden');

  const fd = new FormData();
  fd.append('file', file);
  try {
    await api(endpoint, { method: 'POST', body: fd });
    statusEl.textContent = '✓ 등록 완료';
    statusEl.classList.add('success');
    if (previewImg) {
      previewImg.src = `${endpoint}?t=${Date.now()}`;
      previewImg.style.display = '';
      if (noEl) noEl.style.display = 'none';
    }
    toast('에셋이 등록되었습니다.', 'success');
  } catch (e) {
    statusEl.textContent = `오류: ${e.message}`;
    statusEl.className = 'upload-status error';
    toast(`업로드 실패: ${e.message}`, 'error');
  } finally {
    setTimeout(() => statusEl.classList.add('hidden'), 3000);
  }
}

// ── 아이린 이미지 업로드 ─────────────────────────────────────────────────
$('uploadIrene').addEventListener('change', function () {
  uploadAsset(
    this,
    '/api/assets/irene',
    $('ireneUploadStatus'),
    $('imgIrene'),
    $('noIrene'),
  ).then(() => {
    // 사이드바 아이린 이미지도 갱신
    const sideImg = $('irenePreview');
    if (sideImg) {
      sideImg.src = `/api/assets/irene?t=${Date.now()}`;
      sideImg.style.display = '';
      const fb = $('ireneFallback');
      if (fb) fb.style.display = 'none';
    }
  });
});

// ── KT 로고 업로드 ───────────────────────────────────────────────────────
$('uploadLogo').addEventListener('change', function () {
  uploadAsset(
    this,
    '/api/assets/logo',
    $('logoUploadStatus'),
    $('imgLogo'),
    $('noLogo'),
  );
});

// ── 배경 파일 업로드 + 그리드 ────────────────────────────────────────────
let selectedBg = null;   // 현재 선택된 배경 파일명

async function loadBgGrid() {
  const grid  = $('bgGrid');
  const noEl  = $('noBg');
  try {
    const list = await api('/api/assets/backgrounds');
    if (!list.length) {
      grid.innerHTML = '';
      noEl.style.display = 'flex';
      return;
    }
    noEl.style.display = 'none';
    grid.innerHTML = list.map(item => bgCard(item)).join('');
  } catch { /* 무시 */ }
}

function bgCard(item) {
  const isSelected = selectedBg === item.name;
  const thumb = item.thumb_url
    ? `<img class="bg-thumb" src="${item.thumb_url}" alt="${item.name}" loading="lazy"/>`
    : `<div class="bg-thumb-video">${item.type === 'video' ? '🎬' : '🖼'}</div>`;
  return `
<div class="bg-card${isSelected ? ' selected' : ''}"
     id="bgc_${item.name.replace(/\./g,'_')}"
     onclick="selectBg('${item.name}', this)">
  <span class="bg-card-type">${item.type === 'video' ? 'VID' : 'IMG'}</span>
  ${thumb}
  <div class="bg-card-label">${item.name}</div>
  <button class="bg-card-del" title="삭제"
          onclick="deleteBg(event,'${item.name}')">✕</button>
</div>`;
}

window.selectBg = (name, el) => {
  document.querySelectorAll('.bg-card').forEach(c => c.classList.remove('selected'));
  if (selectedBg === name) {
    selectedBg = null;   // 재클릭 시 선택 해제
  } else {
    selectedBg = name;
    el.classList.add('selected');
    toast(`배경 "${name}" 선택됨`, 'success');
  }
};

window.deleteBg = async (e, name) => {
  e.stopPropagation();
  try {
    await api(`/api/assets/backgrounds/${name}`, { method: 'DELETE' });
    if (selectedBg === name) selectedBg = null;
    await loadBgGrid();
    toast('배경 파일 삭제됨', 'info');
  } catch (err) {
    toast(`삭제 실패: ${err.message}`, 'error');
  }
};

$('uploadBg').addEventListener('change', async function () {
  const file = this.files[0];
  if (!file) return;
  this.value = '';
  const fd = new FormData();
  fd.append('file', file);
  try {
    toast('배경 파일 업로드 중…', 'info');
    await api('/api/assets/backgrounds', { method: 'POST', body: fd });
    await loadBgGrid();
    toast('배경 파일이 추가되었습니다.', 'success');
  } catch (e) {
    toast(`업로드 실패: ${e.message}`, 'error');
  }
});

// ── 구헤더의 아이린 업로드 버튼도 동기화 ────────────────────────────────
const legacyUpload = $('ireneUpload');
if (legacyUpload) {
  legacyUpload.addEventListener('change', function () {
    $('uploadIrene').files = this.files;
    $('uploadIrene').dispatchEvent(new Event('change'));
  });
}

// ── 초기 에셋 상태 로드 ──────────────────────────────────────────────────
async function initAssets() {
  try {
    const status = await api('/api/assets/status');

    // 아이린
    if (status.irene.registered) {
      const url = `/api/assets/irene?t=${Date.now()}`;
      // 에셋 관리 카드
      const img = $('imgIrene');
      if (img) { img.src = url; img.style.display = ''; }
      const no = $('noIrene');
      if (no) no.style.display = 'none';
      // 사이드 패널
      irenePreview.src = url;
      irenePreview.style.display = '';
      $('ireneFallback').style.display = 'none';
    }
    // 로고
    if (status.logo.registered) {
      const img = $('imgLogo');
      if (img) { img.src = `/api/assets/logo?t=${Date.now()}`; img.style.display = ''; }
      const no = $('noLogo');
      if (no) no.style.display = 'none';
    }
  } catch { /* 서버 미기동 시 무시 */ }

  await loadBgGrid();
}

initAssets();
