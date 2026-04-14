let currentProject = null;

const createBtn = document.getElementById('createBtn');
const generateAllBtn = document.getElementById('generateAllBtn');
const renderBtn = document.getElementById('renderBtn');
const projectInfo = document.getElementById('projectInfo');
const sceneList = document.getElementById('sceneList');
const finalResult = document.getElementById('finalResult');
const monitor = document.getElementById('monitor');

function toast(msg, isError = false) {
  finalResult.textContent = msg;
  finalResult.style.background = isError ? '#7a091d' : '#111';
}

async function apiFetch(url, options = {}) {
  const res = await fetch(url, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || `${res.status} ${res.statusText}`);
  }
  return data;
}

function collectProjectPayload() {
  return {
    title: document.getElementById('title').value,
    template: document.getElementById('template').value,
    background: document.getElementById('background').value,
    outfit: document.getElementById('outfit').value,
    hair: document.getElementById('hair').value,
    logo_position: document.getElementById('logo_position').value,
    logo_scale: 12,
    subtitle_font: 'Pretendard',
    target_scene_sec: Number(document.getElementById('target_sec').value),
    script: document.getElementById('script').value,
  };
}

async function updateProjectSettings() {
  if (!currentProject) return;
  const payload = collectProjectPayload();
  const settings = {
    template: payload.template,
    background: payload.background,
    outfit: payload.outfit,
    hair: payload.hair,
    logo_position: payload.logo_position,
    logo_scale: 12,
    subtitle_font: 'Pretendard',
  };

  const project = await apiFetch(`/api/projects/${currentProject.project_id}/settings`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings),
  });
  renderProject(project);
}

function sceneCard(scene) {
  const exceeded = scene.script_text.length > scene.recommended_char_limit;
  const subtitleLink = scene.subtitle_url ? `<a href="${scene.subtitle_url}" target="_blank">자막</a>` : '';
  const audioLink = scene.tts_audio_url ? `<a href="${scene.tts_audio_url}" target="_blank">음성</a>` : '';

  return `
    <div class="scene">
      <div class="scene-head">
        <strong>씬 ${scene.order_index + 1}</strong>
        <span class="meta">${scene.script_text.length}/${scene.recommended_char_limit}자</span>
      </div>
      <textarea id="script_${scene.scene_id}" rows="3">${scene.script_text}</textarea>
      <div class="meta">상태: ${scene.status} | 길이: ${scene.duration_sec.toFixed(2)}s | 버전: v${scene.version}</div>
      ${exceeded ? '<div class="warn">권장 글자수를 초과했습니다.</div>' : ''}
      <label class="meta">발음 사전(JSON)
        <input id="dict_${scene.scene_id}" placeholder='{"KT":"케이티"}' />
      </label>
      <div class="scene-actions">
        <button onclick="updateScene('${scene.scene_id}')">대본 수정</button>
        <button class="primary" onclick="generateScene('${scene.scene_id}')">씬 생성</button>
        ${scene.video_url ? `<a href="${scene.video_url}" target="_blank">씬 영상</a>` : ''}
        ${audioLink}
        ${subtitleLink}
      </div>
    </div>
  `;
}

function renderProject(project) {
  currentProject = project;
  projectInfo.innerHTML = `<b>${project.title}</b> | status: ${project.status} | template: ${project.template}`;
  sceneList.innerHTML = project.scenes.map(sceneCard).join('');
  monitor.textContent = project.final_video_url ? `렌더 완료: ${project.final_video_url}` : '미리보기 화면';
  toast(project.final_video_url ? '최종 렌더 완료' : '프로젝트 업데이트 완료');
}

createBtn.addEventListener('click', async () => {
  try {
    const project = await apiFetch('/api/projects', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(collectProjectPayload()),
    });
    renderProject(project);
  } catch (err) {
    toast(`생성 실패: ${err.message}`, true);
  }
});

window.updateScene = async (sceneId) => {
  if (!currentProject) return toast('프로젝트를 먼저 생성하세요.', true);
  try {
    const script = document.getElementById(`script_${sceneId}`).value;
    const project = await apiFetch(`/api/projects/${currentProject.project_id}/scenes/${sceneId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ script }),
    });
    renderProject(project);
  } catch (err) {
    toast(`씬 수정 실패: ${err.message}`, true);
  }
};

window.generateScene = async (sceneId) => {
  if (!currentProject) return toast('프로젝트를 먼저 생성하세요.', true);
  let pronunciation_dict = {};
  try {
    const raw = document.getElementById(`dict_${sceneId}`).value.trim();
    pronunciation_dict = raw ? JSON.parse(raw) : {};

    const project = await apiFetch(`/api/projects/${currentProject.project_id}/scenes/${sceneId}/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pronunciation_dict }),
    });
    renderProject(project);
  } catch (err) {
    toast(`씬 생성 실패: ${err.message}`, true);
  }
};

generateAllBtn.addEventListener('click', async () => {
  if (!currentProject) return toast('프로젝트를 먼저 생성하세요.', true);
  try {
    await updateProjectSettings();
    const project = await apiFetch(`/api/projects/${currentProject.project_id}/generate-all`, { method: 'POST' });
    renderProject(project);
  } catch (err) {
    toast(`전체 생성 실패: ${err.message}`, true);
  }
});

renderBtn.addEventListener('click', async () => {
  if (!currentProject) return toast('프로젝트를 먼저 생성하세요.', true);
  try {
    await updateProjectSettings();
    const project = await apiFetch(`/api/projects/${currentProject.project_id}/render-final`, { method: 'POST' });
    renderProject(project);
  } catch (err) {
    toast(`렌더 실패: ${err.message}`, true);
  }
});
