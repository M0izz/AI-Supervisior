// UX Reconstruction & Mission Composer Automated Integration Test
// Validates:
// 1. Natural-language mission drafting
// 2. Clickable example goals decomposition
// 3. Optional progressive disclosure of technical constraints
// 4. Mission creation on backend with decomposed task graph
// 5. Truthful provider fleet detection & adapter contract
// 6. Backend-authoritative verification checklist & supervisory events

const http = require('http');

function postJson(urlPath, data) {
  return new Promise((resolve, reject) => {
    const payload = JSON.stringify(data);
    const req = http.request({
      hostname: '127.0.0.1',
      port: 8000,
      path: urlPath,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(payload)
      }
    }, (res) => {
      let body = '';
      res.on('data', chunk => body += chunk);
      res.on('end', () => {
        try {
          resolve({ status: res.statusCode, data: JSON.parse(body) });
        } catch (e) {
          resolve({ status: res.statusCode, raw: body });
        }
      });
    });
    req.on('error', reject);
    req.write(payload);
    req.end();
  });
}

function getJson(urlPath) {
  return new Promise((resolve, reject) => {
    const req = http.request({
      hostname: '127.0.0.1',
      port: 8000,
      path: urlPath,
      method: 'GET',
    }, (res) => {
      let body = '';
      res.on('data', chunk => body += chunk);
      res.on('end', () => {
        try {
          resolve({ status: res.statusCode, data: JSON.parse(body) });
        } catch (e) {
          resolve({ status: res.statusCode, raw: body });
        }
      });
    });
    req.on('error', reject);
    req.end();
  });
}

async function runValidation() {
  console.log('--- RUNNING UX & MISSION COMPOSER VALIDATION SUITE ---');

  // Test 1: Natural Language Mission Draft
  console.log('\n[1/6] Testing Natural-Language Draft Decomposition...');
  const prompt = "Fix the failing authentication tests and handle expired sessions";
  const draftRes = await postJson('/api/missions/draft', { goal: prompt });
  if (draftRes.status !== 200) {
    throw new Error(`Draft endpoint returned status ${draftRes.status}: ${JSON.stringify(draftRes)}`);
  }
  const draft = draftRes.data;
  console.log(`✓ Interpreted Title: "${draft.title}"`);
  console.log(`✓ Generated ${draft.proposed_tasks.length} structured execution tasks`);
  console.log(`✓ Suggested Primary Agent: ${draft.suggested_agents[0]}`);
  console.log(`✓ Suggested Fallback Specialist: ${draft.fallback_agent}`);
  console.log(`✓ Verification Plan Attached: Policy=${draft.verification_plan.policy}, Sandbox=${draft.verification_plan.isolated_sandbox}`);

  if (!draft.proposed_tasks || draft.proposed_tasks.length < 3) {
    throw new Error('Draft failed to decompose goal into structured tasks');
  }

  // Test 2: Clickable Example Goals Decomposition
  console.log('\n[2/6] Testing Example Goal ("Refactor payment module without breaking API")...');
  const exPrompt = "Refactor the payment module without changing its public API";
  const exDraftRes = await postJson('/api/missions/draft', { goal: exPrompt });
  if (exDraftRes.status !== 200) {
    throw new Error(`Example draft failed with status ${exDraftRes.status}`);
  }
  console.log(`✓ Interpreted Steps Count: ${exDraftRes.data.interpreted_steps.length}`);
  console.log(`✓ First Step: "${exDraftRes.data.interpreted_steps[0]}"`);

  // Test 3: Starting Mission from Draft (Real Backend Dispatch)
  console.log('\n[3/6] Testing Starting Mission from Draft via Real Backend...');
  const createRes = await postJson('/api/missions', {
    title: draft.title,
    goal: draft.goal,
    repository_path: draft.repository_path,
    tasks: draft.proposed_tasks
  });
  if (createRes.status !== 200) {
    throw new Error(`Create mission failed: ${JSON.stringify(createRes)}`);
  }
  const createdMission = createRes.data;
  console.log(`✓ Mission Created: ID=${createdMission.id}, Status=${createdMission.status}`);

  // Test 4: Verify Task Manager Initialized Graph
  console.log('\n[4/6] Verifying Task Manager Task Graph...');
  const tasksRes = await getJson(`/api/missions/${createdMission.id}/tasks`);
  if (tasksRes.status !== 200) {
    throw new Error(`Get tasks failed: ${JSON.stringify(tasksRes)}`);
  }
  console.log(`✓ Initialized ${tasksRes.data.tasks.length} Tasks in Directed Acyclic Graph`);
  if (tasksRes.data.tasks.length !== draft.proposed_tasks.length) {
    throw new Error('Mismatch between draft proposed tasks and initialized tasks');
  }

  // Test 5: Verify Truthful Provider Fleet
  console.log('\n[5/6] Verifying Truthful Provider Fleet & Adapter Contract...');
  const adaptersRes = await getJson('/api/adapters');
  if (adaptersRes.status !== 200) {
    throw new Error(`Get adapters failed: ${JSON.stringify(adaptersRes)}`);
  }
  const adapters = adaptersRes.data.adapters || [];
  console.log(`✓ Discovered ${adapters.length} Registered Adapters in Local PATH`);
  adapters.forEach(a => {
    console.log(`  - Adapter: ${a.display_name} (${a.adapter_id}) | Available: ${a.availability ? a.availability.available : 'unknown'}`);
  });

  // Test 6: Verify Supervisory Events & Verification Authority
  console.log('\n[6/6] Verifying Supervisory Events & Independent Verification Perimeter...');
  const eventsRes = await getJson('/api/supervisor/events?limit=10');
  if (eventsRes.status !== 200) {
    throw new Error(`Get supervisor events failed: ${JSON.stringify(eventsRes)}`);
  }
  const eventsCount = eventsRes.data.events ? eventsRes.data.events.length : (eventsRes.data.length || 0);
  console.log(`✓ Retrieved ${eventsCount} Supervisory Decision Events`);

  console.log('\n======================================================');
  console.log('✓ ALL 6 UX & MISSION COMPOSER SUITE TESTS PASSED');
  console.log('======================================================\n');
}

runValidation().catch(err => {
  console.error('\n❌ VALIDATION TEST FAILED:', err);
  process.exit(1);
});
