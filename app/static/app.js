let currentProject = null;

const createBtn = document.getElementById('createBtn');
const renderBtn = document.getElementById('renderBtn');
const projectInfo = document.getElementById('projectInfo');
const sceneList = document.getElementById('sceneList');
const finalResult = document.getElementById('finalResult');

function sceneCard(scene) {
  const exceeded = scene.script_text.length > scene.recommended_char_limit;
  return `
    <div class="scene">
      <div><strong>Scene ${scene.order_index + 1}</strong> <span class="meta">(${scene.script_text.length}/${scene.recommended_char_limit} chars)</span></div>
      <textarea id="script_${scene.scene_id}" rows="3">${scene.script_text}</textarea>
      <div class="meta">status: ${scene.status} | duration: ${scene.duration_sec.toFixed(2)}s | version: v${scene.version}</div>
      ${exceeded ? '<div style="color:#fca5a5;">권장 글자수를 초과했습니다.</div>' : ''}
      <div class="row">
        <button onclick="updateScene('${scene.scene_id}')">대본 수정</button>
        <button onclick="generateScene('${scene.scene_id}')">씬 생성/재생성</button>
        ${scene.video_url ? `<a href="${scene.video_url}" target="_blank"><button>씬 결과 열기</button></a>` : ''}
      </div>
    </div>
  `;
}

function renderProject(project) {
  currentProject = project;
  projectInfo.innerHTML = `<div>Project: <b>${project.title}</b> | template: ${project.template} | status: ${project.status}</div>`;
  sceneList.innerHTML = project.scenes.map(sceneCard).join('');
  renderBtn.disabled = !project.scenes.some(s => s.video_url);
  if (project.final_video_url) {
    finalResult.innerHTML = `<a href="${project.final_video_url}" target="_blank">최종 결과 열기</a>`;
  }
}

createBtn.addEventListener('click', async () => {
  const payload = {
    title: document.getElementById('title').value,
    template: document.getElementById('template').value,
    target_scene_sec: Number(document.getElementById('target_sec').value),
    script: document.getElementById('script').value,
  };

  const res = await fetch('/api/projects', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
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
  const res = await fetch(`/api/projects/${currentProject.project_id}/scenes/${sceneId}/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pronunciation_dict: {} }),
  });
  const project = await res.json();
  renderProject(project);
};

renderBtn.addEventListener('click', async () => {
  const res = await fetch(`/api/projects/${currentProject.project_id}/render-final`, {
    method: 'POST',
  });
  const project = await res.json();
  renderProject(project);
});
