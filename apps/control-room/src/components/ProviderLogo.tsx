import React from 'react';

interface ProviderLogoProps {
  providerId?: string;
  name?: string;
  size?: number;
}

export const ProviderLogo: React.FC<ProviderLogoProps> = ({ providerId, name, size = 18 }) => {
  const id = ((providerId || name || '') as string).toLowerCase();

  // 1. Anthropic / Claude Code
  if (id.includes('claude') || id.includes('anthropic')) {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
        <rect width="24" height="24" rx="5" fill="#D97706" fillOpacity="0.16" />
        <path d="M12 4L14.2 9.4L19.6 11.6L14.2 13.8L12 19.2L9.8 13.8L4.4 11.6L9.8 9.4L12 4Z" fill="#D97706" />
      </svg>
    );
  }

  // 2. OpenAI / Codex
  if (id.includes('codex') || id.includes('openai')) {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
        <rect width="24" height="24" rx="5" fill="#10B981" fillOpacity="0.16" />
        <circle cx="12" cy="12" r="5" stroke="#10B981" strokeWidth="2" strokeDasharray="3 2" />
        <circle cx="12" cy="12" r="2" fill="#10B981" />
      </svg>
    );
  }

  // 3. Google Gemini / Gemma
  if (id.includes('gemini') || id.includes('google') || id.includes('gemma')) {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
        <rect width="24" height="24" rx="5" fill="#3B82F6" fillOpacity="0.16" />
        <path d="M12 3C12 7.97 7.97 12 3 12C7.97 12 12 16.03 12 21C12 16.03 16.03 12 21 12C16.03 12 12 7.97 12 3Z" fill="#3B82F6" />
      </svg>
    );
  }

  // 4. DigitalOcean
  if (id.includes('digitalocean') || id.includes('droplet') || id === 'do') {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
        <rect width="24" height="24" rx="5" fill="#0080FF" fillOpacity="0.16" />
        <path d="M12 4C7.58 4 4 7.58 4 12C4 16.42 7.58 20 12 20C16.42 20 20 16.42 20 12H16C16 14.21 14.21 16 12 16C9.79 16 8 14.21 8 12C8 9.79 9.79 8 12 8V4Z" fill="#0080FF" />
        <rect x="5.5" y="16.5" width="2.5" height="2.5" fill="#0080FF" />
        <rect x="3.5" y="19" width="1.8" height="1.8" fill="#0080FF" />
      </svg>
    );
  }

  // 5. Nous Research / Hermes Agent
  if (id.includes('hermes') || id.includes('nous')) {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
        <rect width="24" height="24" rx="5" fill="#EF4444" fillOpacity="0.16" />
        <path d="M6 8L12 4L18 8V16L12 20L6 16V8Z" stroke="#EF4444" strokeWidth="1.8" strokeLinejoin="round" />
        <path d="M12 4V20M6 8L18 16M6 16L18 8" stroke="#EF4444" strokeWidth="1.2" strokeOpacity="0.7" />
        <circle cx="12" cy="12" r="2.5" fill="#EF4444" />
      </svg>
    );
  }

  // 6. Nebius Token Factory
  if (id.includes('nebius') || id.includes('nemotron')) {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
        <rect width="24" height="24" rx="5" fill="#A855F7" fillOpacity="0.16" />
        <path d="M7 6H17V10H11V14H17V18H7V6Z" fill="#A855F7" />
        <circle cx="17" cy="8" r="1.5" fill="#E9D5FF" />
        <circle cx="17" cy="16" r="1.5" fill="#E9D5FF" />
      </svg>
    );
  }

  // 7. Qwen / Local model
  if (id.includes('qwen') || id.includes('local')) {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
        <rect width="24" height="24" rx="5" fill="#8B5CF6" fillOpacity="0.16" />
        <path d="M12 5L18 8.5V15.5L12 19L6 15.5V8.5L12 5Z" stroke="#8B5CF6" strokeWidth="2" strokeLinejoin="round" />
        <circle cx="12" cy="12" r="2" fill="#8B5CF6" />
      </svg>
    );
  }

  // 8. OpenCode
  if (id.includes('opencode') || id.includes('open')) {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
        <rect width="24" height="24" rx="5" fill="#06B6D4" fillOpacity="0.16" />
        <path d="M8 8L5 12L8 16M16 8L19 12L16 16M14 6L10 18" stroke="#06B6D4" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }

  // 9. Kimi / Moonshot
  if (id.includes('kimi') || id.includes('moonshot')) {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
        <rect width="24" height="24" rx="5" fill="#F59E0B" fillOpacity="0.16" />
        <path d="M16 12C16 15.3137 13.3137 18 10 18C7.65 18 5.62 16.65 4.67 14.7C5.35 14.9 6.06 15 6.8 15C10.22 15 13 12.22 13 8.8C13 8.06 12.9 7.35 12.7 6.67C14.65 7.62 16 9.65 16 12Z" fill="#F59E0B" />
      </svg>
    );
  }

  // 10. Goose / Block
  if (id.includes('goose') || id.includes('block')) {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
        <rect width="24" height="24" rx="5" fill="#14B8A6" fillOpacity="0.16" />
        <path d="M6 14C6 10 9 6 14 6H18V10C18 15 14 18 10 18C8 18 6 16.5 6 14Z" stroke="#14B8A6" strokeWidth="2" strokeLinejoin="round" />
        <circle cx="14" cy="10" r="1.5" fill="#14B8A6" />
      </svg>
    );
  }

  // 11. Cline
  if (id.includes('cline')) {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
        <rect width="24" height="24" rx="5" fill="#6366F1" fillOpacity="0.16" />
        <path d="M12 4L19 12L12 20L5 12L12 4Z" stroke="#6366F1" strokeWidth="2" strokeLinejoin="round" />
        <circle cx="12" cy="12" r="3" fill="#6366F1" />
      </svg>
    );
  }

  // 12. Custom Agent
  if (id.includes('custom')) {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
        <rect width="24" height="24" rx="5" fill="#64748B" fillOpacity="0.16" />
        <circle cx="12" cy="12" r="3" stroke="#64748B" strokeWidth="2" />
        <path d="M12 4V7M12 17V20M4 12H7M17 12H20" stroke="#64748B" strokeWidth="2" strokeLinecap="round" />
      </svg>
    );
  }

  // 13. Cursor
  if (id.includes('cursor')) {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
        <rect width="24" height="24" rx="5" fill="#EC4899" fillOpacity="0.16" />
        <path d="M6 6L17 11L12 13L10 18L6 6Z" fill="#EC4899" stroke="#EC4899" strokeWidth="1.5" strokeLinejoin="round" />
      </svg>
    );
  }

  // 14. Antigravity
  if (id.includes('antigravity')) {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
        <rect width="24" height="24" rx="5" fill="#3B82F6" fillOpacity="0.16" />
        <path d="M12 4L19 18H5L12 4Z" stroke="#3B82F6" strokeWidth="2" strokeLinejoin="round" />
        <path d="M8 21H16" stroke="#3B82F6" strokeWidth="2" strokeLinecap="round" />
      </svg>
    );
  }

  // Fallback generic operational agent mark
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <rect width="24" height="24" rx="5" fill="#64748B" fillOpacity="0.16" />
      <circle cx="12" cy="12" r="4" stroke="#64748B" strokeWidth="2" />
    </svg>
  );
};
