let currentProject = null;

const createBtn = document.getElementById('createBtn');
const generateAllBtn = document.getElementById('generateAllBtn');
const renderBtn = document.getElementById('renderBtn');
const projectInfo = document.getElementById('projectInfo');
const sceneList = document.getElementById('sceneList');
const finalResult = document.getElementById('finalResult');

function collectProjectPayload() {
  return {
    title: document.getElementById('title').value,
    template: document.getElementById('template').value,
    background: document.getElementById('background').value,
    outfit: document.getElementById('outfit').value,
    hair: document.getElementById('hair').value,
    logo_position: document.getElementById('logo_position').value,
    logo_scale: Number(document.getElementById('logo_scale').value),
    subtitle_font: document.getElementById('subtitle_font').value,
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
    logo_scale: payload.logo_scale,
    subtitle_font: payload.subtitle_font,
  };
  const res = await fetch(`/api/projects/${currentProject.project_id}/settings`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings),
  });
  if (res.ok) {
    currentProject = await res.json();
    renderProject(currentProject);
  }
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
      <label class="small">발음 사전(JSON)
        <input id="dict_${scene.scene_id}" placeholder='{"KT":"케이티"}' />
      </label>
      <div class="scene-actions">
        <button onclick="updateScene('${scene.scene_id}')">대본 수정</button>
        <button class="primary" onclick="generateScene('${scene.scene_id}')">씬 생성/재생성</button>
        ${scene.video_url ? `<a href="${scene.video_url}" target="_blank">씬 영상</a>` : ''}
        ${audioLink}
        ${subtitleLink}
      </div>
    </div>
  `;
}

function renderProject(project) {
  currentProject = project;
  projectInfo.innerHTML = `
    <div><b>${project.title}</b></div>
    <div class="meta">status: ${project.status} | template: ${project.template} | bg: ${project.background}</div>
  `;

  sceneList.innerHTML = project.scenes.map(sceneCard).join('');
  renderBtn.disabled = !project.scenes.some((s) => s.video_url);
  generateAllBtn.disabled = project.scenes.length === 0;

  if (project.final_video_url) {
    finalResult.innerHTML = `<a href="${project.final_video_url}" target="_blank">최종 결과 파일 열기</a>`;
  }
}

createBtn.addEventListener('click', async () => {
  const res = await fetch('/api/projects', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(collectProjectPayload()),
  });
  const project = await res.json();
  renderProject(project);
});

window.updateScene = async (sceneId) => {
  const script = document.getElementById(`script_${sceneId}`).value;
  const res = await fetch(`/api/projects/${currentProject.project_id}/scenes/${sceneId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ script }),
  });
  const project = await res.json();
  renderProject(project);
};

window.generateScene = async (sceneId) => {
  let pronunciation_dict = {};
  try {
    const raw = document.getElementById(`dict_${sceneId}`).value.trim();
    pronunciation_dict = raw ? JSON.parse(raw) : {};
  } catch (_) {
    alert('발음 사전은 JSON 형식이어야 합니다. 예: {"KT":"케이티"}');
    return;
  }

  const res = await fetch(`/api/projects/${currentProject.project_id}/scenes/${sceneId}/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pronunciation_dict }),
  });
  const project = await res.json();
  renderProject(project);
};

generateAllBtn.addEventListener('click', async () => {
  await updateProjectSettings();
  const res = await fetch(`/api/projects/${currentProject.project_id}/generate-all`, {
    method: 'POST',
  });
  const project = await res.json();
  renderProject(project);
});

renderBtn.addEventListener('click', async () => {
  await updateProjectSettings();
  const res = await fetch(`/api/projects/${currentProject.project_id}/render-final`, {
    method: 'POST',
  });
  const project = await res.json();
  renderProject(project);
});

['template', 'background', 'outfit', 'hair', 'logo_position', 'logo_scale', 'subtitle_font'].forEach((id) => {
  document.getElementById(id).addEventListener('change', updateProjectSettings);
});
