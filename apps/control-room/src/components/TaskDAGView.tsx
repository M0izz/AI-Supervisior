import React from 'react';
import { 
  CheckCircle2, 
  AlertTriangle, 
  Clock, 
  RotateCw, 
  FileCode, 
  User, 
  ArrowDown, 
  Boxes 
} from 'lucide-react';
import type { Task, TaskStatus } from '../types';

interface TaskDAGViewProps {
  tasks: Task[];
  onSelectTask?: (task: Task) => void;
  selectedTaskId?: string | null;
}

export const TaskDAGView: React.FC<TaskDAGViewProps> = ({
  tasks,
  onSelectTask,
  selectedTaskId
}) => {
  if (!tasks || tasks.length === 0) {
    return (
      <div style={{
        padding: '24px',
        textAlign: 'center',
        color: 'var(--text-muted)',
        fontFamily: 'var(--font-mono)',
        fontSize: '12px',
        border: '1px dashed var(--border-default)',
        borderRadius: '4px'
      }}>
        NO TASKS IN DIRECTED ACYCLIC GRAPH
      </div>
    );
  }

  const getStatusBadge = (status: TaskStatus) => {
    switch (status) {
      case 'COMPLETED':
        return (
          <span className="badge badge-emerald">
            <CheckCircle2 size={11} /> COMPLETED
          </span>
        );
      case 'IN_PROGRESS':
        return (
          <span className="badge badge-cyan">
            <RotateCw size={11} className="spin" /> RUNNING
          </span>
        );
      case 'FAILED':
        return (
          <span className="badge badge-crimson">
            <AlertTriangle size={11} /> FAILED
          </span>
        );
      case 'BLOCKED':
        return (
          <span className="badge badge-amber">
            <AlertTriangle size={11} /> BLOCKED
          </span>
        );
      case 'PENDING':
      default:
        return (
          <span className="badge badge-neutral">
            <Clock size={11} /> PENDING
          </span>
        );
    }
  };

  // Group tasks or layout sequentially respecting dependencies
  // Sort tasks: tasks with 0 dependencies first, then tasks depending on them
  const sortedTasks = [...tasks].sort((a, b) => {
    if (a.dependencies.includes(b.id)) return 1;
    if (b.dependencies.includes(a.id)) return -1;
    return a.id.localeCompare(b.id);
  });

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
      {/* DAG Flow Pipeline */}
      <div style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'stretch',
        gap: '6px'
      }}>
        {sortedTasks.map((task, idx) => {
          const isSelected = selectedTaskId === task.id;
          const hasDependencies = task.dependencies && task.dependencies.length > 0;

          return (
            <React.Fragment key={task.id}>
              {/* Dependency Connection Line */}
              {idx > 0 && (
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  padding: '2px 0',
                  color: 'var(--border-strong)'
                }}>
                  <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '4px',
                    fontFamily: 'var(--font-mono)',
                    fontSize: '10px',
                    color: 'var(--text-muted)'
                  }}>
                    <ArrowDown size={14} color="var(--border-strong)" />
                    {hasDependencies && (
                      <span>depends on: {task.dependencies.join(', ')}</span>
                    )}
                  </div>
                </div>
              )}

              {/* Task Node Card */}
              <div 
                onClick={() => onSelectTask?.(task)}
                style={{
                  backgroundColor: isSelected ? 'var(--bg-surface-elevated)' : 'var(--bg-surface)',
                  border: isSelected ? '1px solid var(--status-cyan)' : '1px solid var(--border-default)',
                  borderRadius: '4px',
                  padding: '12px 16px',
                  cursor: onSelectTask ? 'pointer' : 'default',
                  transition: 'border-color 0.15s ease',
                  boxShadow: isSelected ? '0 0 8px rgba(14, 165, 233, 0.2)' : 'none'
                }}
              >
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  marginBottom: '8px'
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <span style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: '11px',
                      color: 'var(--text-muted)',
                      backgroundColor: 'var(--bg-core)',
                      padding: '2px 6px',
                      borderRadius: '2px',
                      border: '1px solid var(--border-subtle)'
                    }}>
                      TASK-{idx + 1} &bull; {task.id}
                    </span>
                    <strong style={{
                      fontSize: '13px',
                      color: 'var(--text-primary)',
                      fontFamily: 'var(--font-sans)'
                    }}>
                      {task.name}
                    </strong>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    {typeof task.retry_count === 'number' && task.retry_count > 0 && (
                      <span className="badge badge-amber" style={{ fontSize: '10px' }}>
                        RETRIES: {task.retry_count}
                      </span>
                    )}
                    {getStatusBadge(task.status)}
                  </div>
                </div>

                <div style={{
                  fontSize: '12px',
                  color: 'var(--text-secondary)',
                  marginBottom: '10px',
                  fontFamily: 'var(--font-sans)'
                }}>
                  {task.description}
                </div>

                {/* Meta details footer: assigned agent, scope files */}
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  flexWrap: 'wrap',
                  gap: '16px',
                  fontSize: '11px',
                  fontFamily: 'var(--font-mono)',
                  color: 'var(--text-muted)',
                  borderTop: '1px solid var(--border-subtle)',
                  paddingTop: '8px'
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                    <User size={12} color="var(--text-secondary)" />
                    <span>Agent:</span>
                    <span style={{ color: task.assigned_agent_id ? 'var(--status-cyan)' : 'var(--text-muted)' }}>
                      {task.assigned_agent_id || 'UNASSIGNED'}
                    </span>
                  </div>

                  {task.expected_files && task.expected_files.length > 0 && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                      <FileCode size={12} color="var(--text-secondary)" />
                      <span>Scope:</span>
                      <span style={{ color: 'var(--text-primary)' }}>
                        {task.expected_files.join(', ')}
                      </span>
                    </div>
                  )}

                  {task.actual_files_modified && task.actual_files_modified.length > 0 && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                      <Boxes size={12} color="var(--status-amber)" />
                      <span>Modified:</span>
                      <span style={{ color: 'var(--status-amber)' }}>
                        {task.actual_files_modified.join(', ')}
                      </span>
                    </div>
                  )}
                </div>
              </div>
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
};
