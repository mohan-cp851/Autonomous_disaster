(() => {
    const root = document.getElementById('command-center');
    if (!root) return;

    const canOperate = root.dataset.canOperate === 'true';
    const isAdmin = root.dataset.isAdmin === 'true';
    const state = { overview: null, selectedIncidentId: null, map: null, mapLayers: null };
    const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (character) => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[character]));
    const formatDate = (value) => value ? new Date(value).toLocaleString() : 'Not recorded';
    const number = (value, digits = 1) => Number.isFinite(Number(value))
        ? Number(value).toFixed(digits) : 'Unknown';

    async function requestJson(url, options = {}) {
        const response = await fetch(url, {
            ...options,
            headers: {
                ...(options.body ? { 'Content-Type': 'application/json' } : {}),
                ...(options.headers || {})
            }
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok || payload.success === false) {
            throw new Error(payload.error || `Request failed (${response.status}).`);
        }
        return payload;
    }

    function showMessage(message, type = 'success') {
        const element = document.getElementById('command-message');
        element.className = `alert alert-${type}`;
        element.textContent = message;
        element.classList.remove('d-none');
        window.setTimeout(() => element.classList.add('d-none'), 7000);
    }

    function badge(text, variant = 'secondary') {
        return `<span class="badge text-bg-${variant}">${escapeHtml(text)}</span>`;
    }

    function priorityVariant(priority) {
        return ({
            Critical: 'danger', High: 'warning', Moderate: 'info',
            Low: 'secondary', 'Needs Verification': 'dark'
        })[priority] || 'secondary';
    }

    function renderSummary(summary) {
        const cards = [
            ['Active incidents', summary.active_incidents, 'danger'],
            ['Needs verification', summary.needs_verification, 'warning'],
            ['Available teams', summary.available_teams, 'primary'],
            ['Available supply units', summary.available_supply_units, 'success'],
            ['Pending approvals', summary.pending_approvals, 'dark']
        ];
        document.getElementById('summary-cards').innerHTML = cards.map(([label, value, color]) => `
            <div class="col-6 col-lg">
                <div class="card border-0 shadow-sm h-100">
                    <div class="card-body py-3">
                        <div class="small text-muted">${escapeHtml(label)}</div>
                        <div class="h3 mb-0 text-${color}">${escapeHtml(value)}</div>
                    </div>
                </div>
            </div>
        `).join('');
    }

    function renderIncidents(incidents) {
        const rows = document.getElementById('incident-rows');
        rows.innerHTML = incidents.map((incident) => {
            const assessment = incident.priority_assessment;
            const confidence = assessment.evidence.confidence_score;
            const selected = incident.id === state.selectedIncidentId;
            return `
                <tr class="command-incident-row ${selected ? 'is-selected' : ''}" data-incident-id="${incident.id}" tabindex="0">
                    <td>
                        <div class="fw-semibold">${escapeHtml(incident.title)}</div>
                        <div class="small text-muted">${escapeHtml(incident.location_name)} · ${escapeHtml(incident.disaster_type)} · ${formatDate(incident.created_at)}</div>
                    </td>
                    <td>${badge(assessment.priority, priorityVariant(assessment.priority))}<div class="small text-muted mt-1">Score ${assessment.score}/100</div></td>
                    <td>${badge(`${confidence}%`, confidence < 30 ? 'danger' : 'info')}<div class="small text-muted mt-1">${escapeHtml(incident.verification_status)}</div></td>
                    <td>${Number(incident.affected_count) > 0 ? escapeHtml(incident.affected_count) : 'Unknown'}</td>
                </tr>`;
        }).join('');
        document.getElementById('incident-empty').classList.toggle('d-none', incidents.length > 0);
        filterIncidents();
    }

    function renderEvidence(incident) {
        state.selectedIncidentId = incident.id;
        const assessment = incident.priority_assessment;
        document.getElementById('selected-incident-label').textContent =
            `${incident.title} · ${assessment.priority} · ${assessment.evidence.confidence_score}% evidence confidence`;
        const evidencePanel = document.getElementById('evidence-panel');
        const evidence = assessment.evidence;
        const factors = assessment.factors.map((factor) => `
            <li>${escapeHtml(factor.name)}: ${escapeHtml(factor.value)} (${escapeHtml(factor.points)} points)</li>
        `).join('');
        const evidenceRows = evidence.evidence.length ? evidence.evidence.map((item) => `
            <div class="command-evidence-item ${item.is_stale ? 'is-stale' : ''} p-2 mb-2 bg-light rounded">
                <div class="d-flex justify-content-between gap-2">
                    <strong>${escapeHtml(item.source_type)}</strong>
                    ${badge(item.verification_status, item.verification_status === 'Verified' ? 'success' : 'secondary')}
                </div>
                <div class="small mt-1">${escapeHtml(item.description)}</div>
                <div class="small text-muted mt-1">
                    Observed ${formatDate(item.observed_at)}${item.is_stale ? ' · stale (>24h)' : ''}
                    ${item.source_reference ? ` · Ref ${escapeHtml(item.source_reference)}` : ''}
                    ${item.claim_type ? ` · ${escapeHtml(item.claim_type)}: ${escapeHtml(item.claim_value)}` : ''}
                </div>
                ${item.review_note ? `<div class="small text-muted">Review: ${escapeHtml(item.review_note)}</div>` : ''}
                ${canOperate ? `
                    <div class="d-flex flex-wrap gap-1 mt-2">
                        ${['Verified', 'Rejected', 'Inconclusive', 'Superseded'].map((status) =>
                            `<button class="btn btn-sm btn-outline-secondary review-evidence" data-id="${item.id}" data-status="${status}">${status}</button>`
                        ).join('')}
                    </div>` : ''}
            </div>
        `).join('') : '<p class="small text-muted">No evidence reports have been submitted.</p>';
        const conflicts = evidence.conflicts.length ? `
            <div class="alert alert-warning py-2 small">
                <strong>Unresolved conflicting claims</strong>
                ${evidence.conflicts.map((conflict) => `<div>${escapeHtml(conflict.claim_type)}: ${conflict.reports.map((report) =>
                    `${escapeHtml(report.value)} (${escapeHtml(report.source)})`
                ).join(' vs ')}</div>`).join('')}
            </div>` : '';
        const duplicateReports = evidence.potential_duplicate_reports.length
            ? `<div class="small text-warning mb-2">Potential duplicate evidence report groups: ${
                evidence.potential_duplicate_reports.map((group) => group.report_ids.join(' / ')).join(', ')
            }. Review before treating them as independent.</div>` : '';
        const priorityHistory = incident.priority_history?.length ? `
            <details class="small mt-3">
                <summary class="fw-semibold">Previous priority assessments (${incident.priority_history.length})</summary>
                <ul class="mt-2 mb-0">${incident.priority_history.map((item) =>
                    `<li>${escapeHtml(item.priority)} · ${escapeHtml(item.score)}/100 · ${escapeHtml(item.trigger)} · ${formatDate(item.created_at)}</li>`
                ).join('')}</ul>
            </details>` : '';
        evidencePanel.innerHTML = `
            <div class="mb-2">${badge(`${evidence.confidence_score}% evidence confidence`, 'primary')}
                ${badge(incident.verification_status, incident.verification_status === 'Verified' ? 'success' : 'warning')}
            </div>
            <p class="small mb-2">${escapeHtml(evidence.reason)}</p>
            <div class="small text-muted mb-2">${escapeHtml(evidence.label)}</div>
            <div class="small mb-2"><strong>Priority reasoning</strong><ul class="mb-1">${factors}</ul>${escapeHtml(assessment.rationale)}</div>
            ${conflicts}${duplicateReports}
            <div class="small fw-semibold mb-2">Evidence timeline</div>
            ${evidenceRows}
            ${priorityHistory}
        `;
        const evidenceForm = document.getElementById('evidence-form');
        if (evidenceForm) evidenceForm.classList.remove('d-none');
        renderIncidents(state.overview.incidents);
    }

    function renderPlan(plan) {
        const planPanel = document.getElementById('plan-panel');
        const planStatus = document.getElementById('plan-status');
        const actions = document.getElementById('plan-actions');
        if (!plan) {
            planStatus.textContent = 'No plan';
            planStatus.className = 'badge text-bg-secondary';
            planPanel.innerHTML = '<p class="text-muted small">Generate a plan to view team matches, resource shortages, route estimates, and unserved incidents.</p>';
            actions.classList.add('d-none');
            return;
        }
        const statusVariant = plan.status === 'Approved' ? 'success' : plan.status === 'Proposed' ? 'warning' : 'secondary';
        planStatus.textContent = `v${plan.version} · ${plan.status}`;
        planStatus.className = `badge text-bg-${statusVariant}`;
        const assignmentRows = plan.assignments.length ? plan.assignments.map((item) => `
            <div class="command-plan-assignment py-2">
                <div class="d-flex justify-content-between gap-2">
                    <strong>${escapeHtml(item.incident_title)}</strong>
                    ${badge(item.priority, priorityVariant(item.priority))}
                </div>
                <div class="small">${escapeHtml(item.team_name)} · ${item.travel_distance_km === null ? 'Distance unknown' : `${number(item.travel_distance_km, 2)} km`}
                    · ${item.travel_time_min === null ? 'Travel time unknown' : `${number(item.travel_time_min)} min`}</div>
                <div class="small text-muted">${escapeHtml(item.route_status)}. ${escapeHtml(item.rationale)}</div>
            </div>
        `).join('') : '<p class="small text-muted">No feasible team assignments were found.</p>';
        const unserved = plan.unserved_incidents.length ? `
            <div class="alert alert-danger py-2 mt-3 mb-0">
                <strong>Unserved incidents</strong>
                <ul class="small mb-0">${plan.unserved_incidents.map((item) =>
                    `<li>${escapeHtml(item.title)} — ${escapeHtml(item.reason)}</li>`
                ).join('')}</ul>
            </div>` : '<div class="alert alert-success py-2 mt-3 mb-0 small">All active incidents have a team recommendation.</div>';
        const shortageRows = plan.resource_needs.filter((item) => item.shortage_qty > 0);
        const shortages = shortageRows.length ? `
            <div class="alert alert-warning py-2 mt-3 mb-0">
                <strong>Supply shortages</strong>
                <ul class="small mb-0">${shortageRows.map((item) =>
                    `<li>${escapeHtml(item.incident_title)}: ${escapeHtml(item.resource_type)} short ${escapeHtml(item.shortage_qty)} (need ${escapeHtml(item.requested_qty)}, available ${escapeHtml(item.allocated_qty)})</li>`
                ).join('')}</ul>
            </div>` : '<div class="small text-success mt-3">No shortages against the recorded inventory and planning demand.</div>';
        const inventory = state.overview.resources.length ? `
            <details class="mt-3"><summary class="small fw-semibold">Recorded inventory</summary>
                <ul class="small mt-2 mb-0">${state.overview.resources.map((item) =>
                    `<li>${escapeHtml(item.name)}: ${escapeHtml(item.available_qty)} ${escapeHtml(item.resource_type)} available</li>`
                ).join('')}</ul>
            </details>` : '<p class="small text-muted mt-3">No inventory records.</p>';
        planPanel.innerHTML = `
            <div class="small text-muted mb-2">${escapeHtml(plan.trigger)} · ${formatDate(plan.created_at)}</div>
            <div class="small mb-1">Assignments are recommendations only; approval does not dispatch a team.</div>
            ${assignmentRows}${unserved}${shortages}${inventory}
            <div id="plan-comparison" class="mt-3"></div>
        `;
        actions.innerHTML = '';
        if (plan.status === 'Proposed' && isAdmin) {
            actions.innerHTML = `
                <div class="d-flex gap-2 justify-content-end">
                    <button class="btn btn-sm btn-outline-danger" id="reject-plan">Reject proposal</button>
                    <button class="btn btn-sm btn-success" id="approve-plan">Approve proposal</button>
                </div>`;
            actions.classList.remove('d-none');
        } else {
            actions.classList.add('d-none');
        }
        if (plan.previous_plan_id) loadPlanComparison(plan.id);
    }

    async function loadPlanComparison(planId) {
        const container = document.getElementById('plan-comparison');
        if (!container) return;
        try {
            const payload = await requestJson(`/api/command/plans/${planId}/comparison`);
            const comparison = payload.comparison;
            const changes = [
                ...comparison.changed_assignments.map((item) =>
                    `<li>${escapeHtml(item.incident_title)}: ${escapeHtml(item.previous_team_name)} → ${escapeHtml(item.team_name)}</li>`),
                ...comparison.new_assignments.map((item) =>
                    `<li>${escapeHtml(item.incident_title)}: newly assigned to ${escapeHtml(item.team_name)}</li>`),
                ...comparison.removed_assignments.map((item) =>
                    `<li>${escapeHtml(item.incident_title)}: removed from ${escapeHtml(item.previous_team_name)}</li>`),
                ...comparison.retained_assignments.filter((item) => item.route_changed || item.travel_time_change_min !== 0).map((item) =>
                    `<li>${escapeHtml(item.incident_title)}: retained ${escapeHtml(item.team_name)}; travel-time change ${escapeHtml(item.travel_time_change_min)} min</li>`)
            ];
            container.innerHTML = `
                <div class="border-top pt-3">
                    <div class="fw-semibold small">Comparison with plan ${comparison.previous_plan_id ?? 'before planning'}</div>
                    <div class="small text-muted">${comparison.retained_assignments.length} retained · ${comparison.changed_assignments.length} changed · ${comparison.new_assignments.length} new · ${comparison.removed_assignments.length} removed</div>
                    ${changes.length ? `<ul class="small mt-2 mb-0">${changes.join('')}</ul>` : '<div class="small text-muted mt-2">No assignment changes.</div>'}
                    <div class="small mt-2">Unserved: ${comparison.unserved_before.length} before → ${comparison.unserved_after.length} after.</div>
                </div>`;
        } catch (error) {
            container.textContent = `Plan comparison is unavailable: ${error.message}`;
        }
    }

    function renderRoads(roads) {
        const rows = document.getElementById('road-rows');
        rows.innerHTML = roads.map((road) => `
            <tr>
                <td>${escapeHtml(road.name)}</td>
                <td>${badge(road.status, road.status === 'Open' ? 'success' : 'danger')}</td>
                <td class="small">${escapeHtml(road.source_type)}<br>${formatDate(road.updated_at)}</td>
                <td class="text-end">
                    ${canOperate ? `<button class="btn btn-sm ${road.status === 'Closed' ? 'btn-outline-success' : 'btn-outline-danger'} road-status" data-id="${road.id}" data-status="${road.status === 'Closed' ? 'Open' : 'Closed'}">${road.status === 'Closed' ? 'Reopen' : 'Mark inaccessible'}</button>` : ''}
                </td>
            </tr>`).join('');
        document.getElementById('roads-empty').classList.toggle('d-none', roads.length > 0);
    }

    function renderShelters(shelters) {
        const list = document.getElementById('shelter-list');
        list.innerHTML = shelters.length ? shelters.map((shelter) => {
            const occupancy = shelter.capacity > 0
                ? Math.min(100, Math.round(shelter.occupancy / shelter.capacity * 100)) : 0;
            return `
                <div class="mb-3 pb-3 border-bottom">
                    <div class="d-flex justify-content-between gap-2">
                        <strong>${escapeHtml(shelter.name)}</strong>
                        ${badge(shelter.accessibility_status, shelter.accessibility_status === 'Accessible' ? 'success' : shelter.accessibility_status === 'Inaccessible' ? 'danger' : 'warning')}
                    </div>
                    <div class="small text-muted">${escapeHtml(shelter.location_name)} · ${escapeHtml(shelter.vacancy)} available / ${escapeHtml(shelter.capacity)}</div>
                    <div class="progress mt-2" role="progressbar" aria-label="Shelter occupancy" aria-valuenow="${occupancy}" aria-valuemin="0" aria-valuemax="100">
                        <div class="progress-bar ${occupancy >= 90 ? 'bg-danger' : 'bg-info'}" style="width:${occupancy}%">${occupancy}% occupied</div>
                    </div>
                    <div class="small text-muted mt-1">Information: ${escapeHtml(shelter.information_freshness)}${shelter.information_updated_at ? ` · ${formatDate(shelter.information_updated_at)}` : ''}${shelter.information_source ? ` · ${escapeHtml(shelter.information_source)}` : ''}</div>
                    ${canOperate ? `
                        <div class="d-flex gap-2 mt-2">
                            <select class="form-select form-select-sm shelter-accessibility" data-id="${shelter.id}" aria-label="Shelter accessibility">
                                ${['Accessible', 'Inaccessible', 'Unknown'].map((status) => `<option ${status === shelter.accessibility_status ? 'selected' : ''}>${status}</option>`).join('')}
                            </select>
                            <button class="btn btn-sm btn-outline-primary update-shelter" data-id="${shelter.id}">Update</button>
                        </div>` : ''}
                </div>`;
        }).join('') : '<p class="text-muted small mb-0">No shelters are recorded.</p>';
    }

    function renderActivity(events, auditRecords) {
        document.getElementById('event-list').innerHTML = events.length ? events.map((event) => `
            <div class="list-group-item">
                <div class="fw-semibold small">${escapeHtml(event.event_type.replaceAll('_', ' '))}</div>
                <div class="small text-muted">${escapeHtml(event.source_type)} · ${formatDate(event.created_at)}</div>
                <div class="small">${escapeHtml(event.details.segment_name || '')} ${escapeHtml(event.details.previous_status || '')} → ${escapeHtml(event.details.requested_status || '')}</div>
            </div>`).join('') : '<div class="list-group-item small text-muted">No replan events recorded.</div>';
        document.getElementById('audit-list').innerHTML = auditRecords.length ? auditRecords.map((record) => `
            <div class="list-group-item">
                <div class="fw-semibold small">${escapeHtml(record.action.replaceAll('.', ' '))}</div>
                <div class="small text-muted">${escapeHtml(record.object_type)} ${record.object_id ? `#${escapeHtml(record.object_id)}` : ''} · ${formatDate(record.created_at)}</div>
                <div class="small">${escapeHtml(JSON.stringify(record.details))}</div>
            </div>`).join('') : '<div class="list-group-item small text-muted">No audit records recorded.</div>';
    }

    function renderMap(overview) {
        const container = document.getElementById('command-map');
        if (!window.L) {
            container.innerHTML = '<div class="p-3 text-muted">Map library unavailable. Operational records remain available in the tables.</div>';
            return;
        }
        if (!state.map) {
            state.map = L.map(container).setView([18.52, 73.8567], 10);
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: '&copy; OpenStreetMap contributors',
                maxZoom: 19
            }).addTo(state.map);
            state.mapLayers = L.layerGroup().addTo(state.map);
        }
        state.mapLayers.clearLayers();
        const bounds = [];
        overview.roads.forEach((road) => {
            const color = road.status === 'Open' ? '#198754' : '#dc3545';
            L.polyline([road.start, road.end], { color, weight: 5, opacity: 0.75 })
                .bindPopup(`${escapeHtml(road.name)} · ${escapeHtml(road.status)} · ${escapeHtml(road.source_type)}`)
                .addTo(state.mapLayers);
            bounds.push(road.start, road.end);
        });
        overview.incidents.forEach((incident) => {
            const marker = L.circleMarker([incident.latitude, incident.longitude], {
                radius: 8,
                color: incident.priority_assessment.priority === 'Critical' ? '#dc3545' : '#fd7e14',
                fillOpacity: 0.8
            }).bindPopup(`${escapeHtml(incident.title)} · ${escapeHtml(incident.priority_assessment.priority)}`);
            marker.addTo(state.mapLayers);
            bounds.push([incident.latitude, incident.longitude]);
        });
        overview.teams.forEach((team) => {
            L.circleMarker([team.latitude, team.longitude], {
                radius: 5, color: '#0d6efd', fillOpacity: 0.7
            }).bindPopup(`${escapeHtml(team.name)} · ${escapeHtml(team.status)}`).addTo(state.mapLayers);
            bounds.push([team.latitude, team.longitude]);
        });
        overview.shelters.forEach((shelter) => {
            L.marker([shelter.latitude, shelter.longitude])
                .bindPopup(`${escapeHtml(shelter.name)} · ${escapeHtml(shelter.vacancy)} places available · ${escapeHtml(shelter.accessibility_status)}`)
                .addTo(state.mapLayers);
            bounds.push([shelter.latitude, shelter.longitude]);
        });
        const plan = overview.pending_plan || overview.latest_plan;
        if (plan) {
            plan.assignments.forEach((assignment) => {
                if (assignment.route_geometry.length > 1) {
                    L.polyline(assignment.route_geometry, { color: '#6f42c1', weight: 4, dashArray: '6 5' })
                        .bindPopup(`Proposed route: ${escapeHtml(assignment.incident_title)} · ${escapeHtml(assignment.team_name)} · ${escapeHtml(assignment.route_status)}`)
                        .addTo(state.mapLayers);
                    bounds.push(...assignment.route_geometry);
                }
            });
        }
        if (bounds.length) state.map.fitBounds(bounds, { padding: [20, 20], maxZoom: 13 });
        window.setTimeout(() => state.map.invalidateSize(), 50);
    }

    function filterIncidents() {
        const query = document.getElementById('incident-search').value.trim().toLowerCase();
        document.querySelectorAll('.command-incident-row').forEach((row) => {
            row.classList.toggle('d-none', !row.textContent.toLowerCase().includes(query));
        });
    }

    async function loadOverview() {
        document.getElementById('command-loading').classList.remove('d-none');
        document.getElementById('command-data').classList.add('d-none');
        try {
            state.overview = await requestJson('/api/command/overview');
            document.getElementById('command-loading').classList.add('d-none');
            document.getElementById('command-data').classList.remove('d-none');
            renderSummary(state.overview.summary);
            renderIncidents(state.overview.incidents);
            renderRoads(state.overview.roads);
            renderShelters(state.overview.shelters);
            renderActivity(state.overview.recent_events, state.overview.recent_audit);
            renderPlan(state.overview.pending_plan || state.overview.latest_plan);
            renderMap(state.overview);
            if (state.selectedIncidentId) {
                const incident = state.overview.incidents.find((item) => item.id === state.selectedIncidentId);
                if (incident) renderEvidence(incident);
            }
        } catch (error) {
            document.getElementById('command-loading').classList.add('d-none');
            showMessage(error.message, 'danger');
        }
    }

    async function submitIncident(event) {
        event.preventDefault();
        const body = {
            title: document.getElementById('incident-title').value.trim(),
            disaster_type: document.getElementById('incident-type').value,
            severity: document.getElementById('incident-severity').value,
            source_type: document.getElementById('incident-source').value,
            affected_count: Number(document.getElementById('incident-affected').value),
            latitude: Number(document.getElementById('incident-latitude').value),
            longitude: Number(document.getElementById('incident-longitude').value),
            location_name: document.getElementById('incident-location').value.trim(),
            description: document.getElementById('incident-description').value.trim()
        };
        try {
            const result = await requestJson('/api/command/incidents', {
                method: 'POST', body: JSON.stringify(body)
            });
            document.getElementById('incident-form').reset();
            showMessage(`Incident recorded. ${result.potential_duplicates.length} potential duplicate(s) need review.`);
            await loadOverview();
        } catch (error) {
            showMessage(error.message, 'danger');
        }
    }

    async function submitEvidence(event) {
        event.preventDefault();
        if (!state.selectedIncidentId) return;
        const body = {
            source_type: document.getElementById('evidence-source').value,
            source_reference: document.getElementById('evidence-reference').value.trim(),
            claim_type: document.getElementById('evidence-claim-type').value.trim(),
            claim_value: document.getElementById('evidence-claim-value').value.trim(),
            description: document.getElementById('evidence-description').value.trim()
        };
        try {
            await requestJson(`/api/command/incidents/${state.selectedIncidentId}/evidence`, {
                method: 'POST', body: JSON.stringify(body)
            });
            document.getElementById('evidence-form').reset();
            showMessage('Evidence report recorded; confidence and priority were recalculated.');
            await loadOverview();
        } catch (error) {
            showMessage(error.message, 'danger');
        }
    }

    async function optimizePlan() {
        try {
            const result = await requestJson('/api/command/plans/optimize', {
                method: 'POST', body: JSON.stringify({})
            });
            showMessage(`Plan v${result.plan.version} proposed. ${result.plan.unserved_incidents.length} incident(s) remain unserved.`);
            await loadOverview();
        } catch (error) {
            showMessage(error.message, 'danger');
        }
    }

    async function decidePlan(decision) {
        const plan = state.overview.pending_plan;
        if (!plan) return;
        if (!window.confirm(`${decision} plan v${plan.version}? This records approval only and does not dispatch teams.`)) return;
        const reason = window.prompt('Optional decision note:', '') || '';
        try {
            await requestJson(`/api/command/plans/${plan.id}/decision`, {
                method: 'POST',
                body: JSON.stringify({ decision, reason })
            });
            showMessage(`Plan ${decision.toLowerCase()} and decision recorded.`);
            await loadOverview();
        } catch (error) {
            showMessage(error.message, 'danger');
        }
    }

    async function updateRoad(button) {
        const status = button.dataset.status;
        const roadName = button.closest('tr').cells[0].textContent;
        if (!window.confirm(`Mark "${roadName}" ${status === 'Closed' ? 'inaccessible' : 'open'}? Affected routes will be recalculated.`)) return;
        const eventId = window.crypto?.randomUUID
            ? window.crypto.randomUUID()
            : `road-${Date.now()}-${Math.random().toString(16).slice(2)}`;
        try {
            const result = await requestJson(`/api/command/roads/${button.dataset.id}/status`, {
                method: 'POST',
                body: JSON.stringify({ event_id: eventId, status, source_type: 'Field Team' })
            });
            showMessage(result.message);
            await loadOverview();
        } catch (error) {
            showMessage(error.message, 'danger');
        }
    }

    document.getElementById('refresh-command-center').addEventListener('click', loadOverview);
    document.getElementById('incident-search').addEventListener('input', filterIncidents);
    document.getElementById('incident-rows').addEventListener('click', (event) => {
        const row = event.target.closest('.command-incident-row');
        if (!row) return;
        const incident = state.overview.incidents.find((item) => item.id === Number(row.dataset.incidentId));
        if (incident) renderEvidence(incident);
    });
    document.getElementById('incident-rows').addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') event.target.closest('.command-incident-row')?.click();
    });
    document.getElementById('road-rows').addEventListener('click', (event) => {
        const button = event.target.closest('.road-status');
        if (button) updateRoad(button);
    });
    document.getElementById('evidence-panel').addEventListener('click', async (event) => {
        const button = event.target.closest('.review-evidence');
        if (!button) return;
        const reason = window.prompt(`Optional reason for marking this report ${button.dataset.status}:`, '') || '';
        try {
            await requestJson(`/api/command/evidence/${button.dataset.id}/review`, {
                method: 'POST',
                body: JSON.stringify({ status: button.dataset.status, reason })
            });
            showMessage('Evidence review recorded and incident status recalculated.');
            await loadOverview();
        } catch (error) {
            showMessage(error.message, 'danger');
        }
    });
    document.getElementById('plan-actions').addEventListener('click', (event) => {
        if (event.target.closest('#approve-plan')) decidePlan('Approved');
        if (event.target.closest('#reject-plan')) decidePlan('Rejected');
    });
    const incidentForm = document.getElementById('incident-form');
    if (incidentForm) incidentForm.addEventListener('submit', submitIncident);
    const evidenceForm = document.getElementById('evidence-form');
    if (evidenceForm) evidenceForm.addEventListener('submit', submitEvidence);
    const optimizeButton = document.getElementById('optimize-plan');
    if (optimizeButton) optimizeButton.addEventListener('click', optimizePlan);

    const demoButton = document.getElementById('initialize-demo');
    if (demoButton) demoButton.addEventListener('click', async () => {
        const scenario = document.getElementById('demo-scenario').value;
        const city = scenario === 'chennai' ? 'Chennai' : 'Pune';
        if (!window.confirm(`Load the deterministic simulated ${city} scenario? It will add labeled demonstration records and will not delete existing data.`)) return;
        try {
            const result = await requestJson('/api/command/demo', {
                method: 'POST', body: JSON.stringify({ scenario })
            });
            showMessage(result.message || 'Simulated scenario is ready.');
            await loadOverview();
        } catch (error) {
            showMessage(error.message, 'danger');
        }
    });

    document.getElementById('shelter-list').addEventListener('click', async (event) => {
        const button = event.target.closest('.update-shelter');
        if (!button) return;
        const select = document.querySelector(`.shelter-accessibility[data-id="${button.dataset.id}"]`);
        try {
            await requestJson(`/api/command/shelters/${button.dataset.id}/condition`, {
                method: 'POST',
                body: JSON.stringify({
                    accessibility_status: select.value,
                    information_source: 'Coordinator update'
                })
            });
            showMessage('Shelter accessibility status updated.');
            await loadOverview();
        } catch (error) {
            showMessage(error.message, 'danger');
        }
    });

    loadOverview();
})();
