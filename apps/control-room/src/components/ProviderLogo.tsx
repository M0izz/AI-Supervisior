import React from 'react';

interface ProviderLogoProps {
  providerId?: string;
  name?: string;
  size?: number;
}

export const ProviderLogo: React.FC<ProviderLogoProps> = ({ providerId, name, size = 18 }) => {
  const id = ((providerId || name || '') as string).toLowerCase();

  // Normalized color & SVG per provider
  if (id.includes('claude')) {
    // Anthropic / Claude warm terracotta mark
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
        <rect width="24" height="24" rx="5" fill="#D97706" fillOpacity="0.16" />
        <path d="M12 4L14.2 9.4L19.6 11.6L14.2 13.8L12 19.2L9.8 13.8L4.4 11.6L9.8 9.4L12 4Z" fill="#D97706" />
      </svg>
    );
  }

  if (id.includes('codex') || id.includes('openai')) {
    // OpenAI / Codex emerald teal mark
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
        <rect width="24" height="24" rx="5" fill="#10B981" fillOpacity="0.16" />
        <circle cx="12" cy="12" r="5" stroke="#10B981" strokeWidth="2" strokeDasharray="3 2" />
        <circle cx="12" cy="12" r="2" fill="#10B981" />
      </svg>
    );
  }

  if (id.includes('gemini') || id.includes('google')) {
    // Google Gemini blue-indigo spark
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
        <rect width="24" height="24" rx="5" fill="#3B82F6" fillOpacity="0.16" />
        <path d="M12 3C12 7.97 7.97 12 3 12C7.97 12 12 16.03 12 21C12 16.03 16.03 12 21 12C16.03 12 12 7.97 12 3Z" fill="#3B82F6" />
      </svg>
    );
  }

  if (id.includes('qwen') || id.includes('local')) {
    // Qwen / Local model violet hex
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
        <rect width="24" height="24" rx="5" fill="#8B5CF6" fillOpacity="0.16" />
        <path d="M12 5L18 8.5V15.5L12 19L6 15.5V8.5L12 5Z" stroke="#8B5CF6" strokeWidth="2" strokeLinejoin="round" />
        <circle cx="12" cy="12" r="2" fill="#8B5CF6" />
      </svg>
    );
  }

  if (id.includes('opencode') || id.includes('open')) {
    // OpenCode cyan terminal brackets
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
        <rect width="24" height="24" rx="5" fill="#06B6D4" fillOpacity="0.16" />
        <path d="M8 8L5 12L8 16M16 8L19 12L16 16M14 6L10 18" stroke="#06B6D4" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }

  if (id.includes('kimi') || id.includes('moonshot')) {
    // Kimi / Moonshot amber crescent
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
        <rect width="24" height="24" rx="5" fill="#F59E0B" fillOpacity="0.16" />
        <path d="M16 12C16 15.3137 13.3137 18 10 18C7.65 18 5.62 16.65 4.67 14.7C5.35 14.9 6.06 15 6.8 15C10.22 15 13 12.22 13 8.8C13 8.06 12.9 7.35 12.7 6.67C14.65 7.62 16 9.65 16 12Z" fill="#F59E0B" />
      </svg>
    );
  }

  if (id.includes('cursor')) {
    // Cursor minimal directional pointer
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
        <rect width="24" height="24" rx="5" fill="#EC4899" fillOpacity="0.16" />
        <path d="M6 6L17 11L12 13L10 18L6 6Z" fill="#EC4899" stroke="#EC4899" strokeWidth="1.5" strokeLinejoin="round" />
      </svg>
    );
  }

  if (id.includes('antigravity')) {
    // Antigravity levitating delta
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
        <rect width="24" height="24" rx="5" fill="#3B82F6" fillOpacity="0.16" />
        <path d="M12 4L19 18H5L12 4Z" stroke="#3B82F6" strokeWidth="2" strokeLinejoin="round" />
        <path d="M8 21H16" stroke="#3B82F6" strokeWidth="2" strokeLinecap="round" />
      </svg>
    );
  }

  // Fallback worker mark
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <rect width="24" height="24" rx="5" fill="#64748B" fillOpacity="0.16" />
      <circle cx="12" cy="12" r="4" stroke="#64748B" strokeWidth="2" />
    </svg>
  );
};
