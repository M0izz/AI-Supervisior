import React, { useState, useEffect } from 'react';
import { X, Cloud, RefreshCw, Laptop, ShieldCheck, CheckCircle2 } from 'lucide-react';
import { triggerSync, getSyncDevices } from '../api';
import type { SyncStatus, SyncDevice } from '../types';

interface SyncModalProps {
  isOpen: boolean;
  onClose: () => void;
  syncStatus: SyncStatus | null;
  onRefreshSync: () => void;
}

export const SyncModal: React.FC<SyncModalProps> = ({
  isOpen,
  onClose,
  syncStatus,
  onRefreshSync
}) => {
  const [devices, setDevices] = useState<SyncDevice[]>([]);
  const [isSyncing, setIsSyncing] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      getSyncDevices()
        .then(res => {
          if (res?.devices) setDevices(res.devices);
        })
        .catch(() => {});
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleManualSync = async () => {
    setIsSyncing(true);
    setMsg(null);
    try {
      await triggerSync();
      onRefreshSync();
      setMsg('Changes synced across peer devices');
    } catch (e: any) {
      setMsg(e.message || 'Sync failed');
    } finally {
      setIsSyncing(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={e => e.stopPropagation()} style={{ maxWidth: '480px' }}>
        <div className="modal-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Cloud size={16} color="var(--primary)" />
            <h2>Cloud Sync & Multi-Device</h2>
          </div>
          <button className="btn btn-ghost btn-sm" onClick={onClose}>
            <X size={16} />
          </button>
        </div>

        <div className="modal-body">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 14px', borderRadius: '8px', backgroundColor: 'var(--surface-elevated)', border: '1px solid var(--border)' }}>
            <div>
              <div style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-primary)' }}>
                This Device
              </div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', marginTop: '2px' }}>
                {syncStatus?.device_id || 'local-host-node'}
              </div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <div className="status-pill" style={{ fontSize: '11px' }}>
                <span className={`status-dot ${syncStatus?.state === 'SYNCED' ? 'active' : 'watching'}`} />
                <span>{syncStatus?.state || 'Active'}</span>
              </div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>
                Last synced: {syncStatus?.last_synced_at ? new Date(syncStatus.last_synced_at).toLocaleTimeString() : 'Just now'}
              </div>
            </div>
          </div>

          {msg && (
            <div style={{ padding: '8px 12px', borderRadius: '6px', backgroundColor: 'var(--primary-subtle)', border: '1px solid var(--primary-border)', color: 'var(--primary)', fontSize: '12px', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <CheckCircle2 size={14} />
              <span>{msg}</span>
            </div>
          )}

          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '4px' }}>
            <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              Registered Devices
            </div>

            {devices.length === 0 ? (
              <div style={{ fontSize: '12px', color: 'var(--text-muted)', padding: '12px', textAlign: 'center', backgroundColor: 'var(--bg)', borderRadius: '6px', border: '1px dashed var(--border)' }}>
                Local supervisor authoritative. Peer devices connect via local-first sync.
              </div>
            ) : (
              devices.map(d => (
                <div key={d.device_id} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 12px', backgroundColor: 'var(--surface-elevated)', borderRadius: '6px', border: '1px solid var(--border-subtle)', fontSize: '12px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <Laptop size={14} color="var(--text-muted)" />
                    <div>
                      <div style={{ fontWeight: 500 }}>{d.display_name}</div>
                      <div style={{ fontSize: '10px', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>{d.platform}</div>
                    </div>
                  </div>
                  <span className="badge badge-neutral" style={{ fontSize: '10px' }}>{d.status}</span>
                </div>
              ))
            )}
          </div>

          <div style={{ fontSize: '11px', color: 'var(--text-muted)', lineHeight: '1.5', marginTop: '6px' }}>
            <ShieldCheck size={12} style={{ display: 'inline', marginRight: '4px', verticalAlign: 'middle' }} />
            The local Supervisor remains authoritative for execution, safety policy, and permissions. Cloud sync only replicates mission history, project memory, and verification records across your devices.
          </div>
        </div>

        <div className="modal-footer">
          <button className="btn btn-secondary btn-sm" onClick={onClose}>
            Close
          </button>
          <button className="btn btn-primary btn-sm" onClick={handleManualSync} disabled={isSyncing}>
            <RefreshCw size={12} className={isSyncing ? 'spin' : ''} />
            <span>{isSyncing ? 'Syncing...' : 'Sync Now'}</span>
          </button>
        </div>
      </div>
    </div>
  );
};
