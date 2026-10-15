import React from 'react';

interface ProviderLogoProps {
  providerId?: string;
  name?: string;
  size?: number;
}

export const ProviderLogo: React.FC<ProviderLogoProps> = ({ providerId, name, size = 32 }) => {
  const id = ((providerId || name || '') as string).toLowerCase();

  // 1. Anthropic / Claude Code — Authentic Anthropic Asterisk / Spark mark
  if (id.includes('claude') || id.includes('anthropic')) {
    return (
      <svg width={size} height={size} viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path
          d="M23.1 7.2L20 12.8L16.9 7.2C16.4 6.3 15.3 5.9 14.4 6.4C13.5 6.9 13.1 8 13.6 8.9L16.8 14.6H10.4C9.4 14.6 8.5 15.5 8.5 16.5C8.5 17.5 9.4 18.4 10.4 18.4H16.8L13.6 24.1C13.1 25 13.5 26.1 14.4 26.6C15.3 27.1 16.4 26.7 16.9 25.8L20 20.2L23.1 25.8C23.6 26.7 24.7 27.1 25.6 26.6C26.5 26.1 26.9 25 26.4 24.1L23.2 18.4H29.6C30.6 18.4 31.5 17.5 31.5 16.5C31.5 15.5 30.6 14.6 29.6 14.6H23.2L26.4 8.9C26.9 8 26.5 6.9 25.6 6.4C24.7 5.9 23.6 6.3 23.1 7.2Z"
          fill="#D97706"
        />
        <circle cx="20" cy="16.5" r="2.8" fill="#F59E0B" />
      </svg>
    );
  }

  // 2. OpenAI / Codex — Authentic OpenAI Spiral Knot mark
  if (id.includes('codex') || id.includes('openai')) {
    return (
      <svg width={size} height={size} viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
        <g stroke="#10B981" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M28.5 17.3V12.7C28.5 11.2 27.3 10 25.8 10H21.2" />
          <path d="M12.7 28.5H17.3C18.8 28.5 20 27.3 20 25.8V21.2" />
          <path d="M22.7 28.5H27.3C28.8 28.5 30 27.3 30 25.8V21.2" />
          <path d="M11.5 22.7V18.1C11.5 16.6 12.7 15.4 14.2 15.4H18.8" />
          <path d="M17.3 11.5H12.7C11.2 11.5 10 12.7 10 14.2V18.8" />
          <path d="M27.3 11.5L20 7.3L12.7 11.5" />
          <path d="M27.3 28.5L20 32.7L12.7 28.5" />
          <path d="M10 14.2L20 20L30 14.2" />
          <path d="M10 25.8L20 20L30 25.8" />
        </g>
        <circle cx="20" cy="20" r="3" fill="#10B981" />
      </svg>
    );
  }

  // 3. Cursor — Authentic 3D Isometric Cube / Arrow mark
  if (id.includes('cursor')) {
    return (
      <svg width={size} height={size} viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
        <g transform="translate(4, 4)">
          {/* Top isometric facet */}
          <path d="M16 2L30 10L16 18L2 10L16 2Z" fill="#F43F5E" fillOpacity="0.85" stroke="#FDA4AF" strokeWidth="1.2" />
          {/* Left isometric facet */}
          <path d="M2 10L16 18V32L2 24V10Z" fill="#BE123C" stroke="#FDA4AF" strokeWidth="1.2" />
          {/* Right isometric facet */}
          <path d="M16 18L30 10V24L16 32V18Z" fill="#E11D48" stroke="#FDA4AF" strokeWidth="1.2" />
          {/* Center laser point */}
          <circle cx="16" cy="18" r="2.2" fill="#FFFFFF" />
        </g>
      </svg>
    );
  }

  // 4. Google Gemini — Authentic 4-pointed hypocycloid star
  if (id.includes('gemini') || id.includes('google') || id.includes('gemma')) {
    return (
      <svg width={size} height={size} viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <linearGradient id="geminiGrad" x1="6" y1="6" x2="34" y2="34" gradientUnits="userSpaceOnUse">
            <stop stopColor="#38BDF8" />
            <stop offset="0.5" stopColor="#3B82F6" />
            <stop offset="1" stopColor="#818CF8" />
          </linearGradient>
        </defs>
        <path
          d="M20 4C20 12.8366 12.8366 20 4 20C12.8366 20 20 27.1634 20 36C20 27.1634 27.1634 20 36 20C27.1634 20 20 12.8366 20 4Z"
          fill="url(#geminiGrad)"
        />
        <circle cx="20" cy="20" r="3" fill="#FFFFFF" fillOpacity="0.9" />
      </svg>
    );
  }

  // 5. Cognition Devin — Authentic Devin Square & Code bracket mark
  if (id.includes('devin') || id.includes('cognition')) {
    return (
      <svg width={size} height={size} viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect x="7" y="7" width="26" height="26" rx="6" fill="#18181B" stroke="#06B6D4" strokeWidth="2" />
        <path d="M15 15L11 20L15 25" stroke="#22D3EE" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M25 15L29 20L25 25" stroke="#22D3EE" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M22 13L18 27" stroke="#38BDF8" strokeWidth="2" strokeLinecap="round" />
      </svg>
    );
  }

  // 6. Windsurf / Codeium — Authentic Wave Flow mark
  if (id.includes('windsurf') || id.includes('codeium')) {
    return (
      <svg width={size} height={size} viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <linearGradient id="windsurfGrad" x1="8" y1="8" x2="32" y2="32" gradientUnits="userSpaceOnUse">
            <stop stopColor="#06B6D4" />
            <stop offset="1" stopColor="#10B981" />
          </linearGradient>
        </defs>
        <path
          d="M8 24C12 24 14 16 18 16C22 16 24 24 28 24C30 24 31 22 32 20M8 18C12 18 14 10 18 10C22 10 24 18 28 18C30 18 31 16 32 14M8 30C12 30 14 22 18 22C22 22 24 30 28 30C30 30 31 28 32 26"
          stroke="url(#windsurfGrad)"
          strokeWidth="2.8"
          strokeLinecap="round"
        />
      </svg>
    );
  }

  // 7. Cline — Authentic Robotic Helmet Visor mark
  if (id.includes('cline')) {
    return (
      <svg width={size} height={size} viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path
          d="M20 7L31 13.5V26.5L20 33L9 26.5V13.5L20 7Z"
          fill="#4F46E5"
          fillOpacity="0.2"
          stroke="#818CF8"
          strokeWidth="2.2"
          strokeLinejoin="round"
        />
        <rect x="13" y="17" width="14" height="6" rx="3" fill="#A5B4FC" />
        <circle cx="17" cy="20" r="1.5" fill="#1E1B4B" />
        <circle cx="23" cy="20" r="1.5" fill="#1E1B4B" />
      </svg>
    );
  }

  // 8. Nous Research / Hermes Agent — Winged Geometric Helm mark
  if (id.includes('hermes') || id.includes('nous')) {
    return (
      <svg width={size} height={size} viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path
          d="M20 6L9 12V22L20 34L31 22V12L20 6Z"
          stroke="#EF4444"
          strokeWidth="2"
          strokeLinejoin="round"
          fill="#EF4444"
          fillOpacity="0.15"
        />
        <path d="M9 12L20 24L31 12" stroke="#F87171" strokeWidth="1.8" />
        <path d="M20 6V24" stroke="#F87171" strokeWidth="2" />
        <circle cx="20" cy="24" r="3" fill="#EF4444" />
      </svg>
    );
  }

  // 9. DigitalOcean Managed Agent — Authentic DO 'D' with trailing pixel blocks
  if (id.includes('digitalocean') || id.includes('droplet') || id === 'do') {
    return (
      <svg width={size} height={size} viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path
          d="M20 8C13.37 8 8 13.37 8 20C8 26.63 13.37 32 20 32C26.63 32 32 26.63 32 20H26C26 23.31 23.31 26 20 26C16.69 26 14 23.31 14 20C14 16.69 16.69 14 20 14V8Z"
          fill="#0080FF"
        />
        <rect x="9" y="27" width="4" height="4" fill="#0080FF" />
        <rect x="6" y="31" width="3" height="3" fill="#0080FF" />
      </svg>
    );
  }

  // 10. Goose / Block — Flying origami bird geometry
  if (id.includes('goose') || id.includes('block')) {
    return (
      <svg width={size} height={size} viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path
          d="M10 24C10 16 15 10 24 10H30V16C30 25 24 30 16 30C12.5 30 10 27.5 10 24Z"
          fill="#14B8A6"
          fillOpacity="0.2"
          stroke="#2DD4BF"
          strokeWidth="2.2"
          strokeLinejoin="round"
        />
        <circle cx="24" cy="16" r="2.5" fill="#2DD4BF" />
        <path d="M10 24L24 16" stroke="#2DD4BF" strokeWidth="1.8" />
      </svg>
    );
  }

  // 11. Qwen / Alibaba Local — Interlocking molecular hexagon
  if (id.includes('qwen') || id.includes('local')) {
    return (
      <svg width={size} height={size} viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path
          d="M20 8L30 14V26L20 32L10 26V14L20 8Z"
          stroke="#8B5CF6"
          strokeWidth="2.2"
          strokeLinejoin="round"
          fill="#8B5CF6"
          fillOpacity="0.15"
        />
        <circle cx="20" cy="20" r="3.5" fill="#A78BFA" />
        <path d="M20 8V16.5M30 26L23 22M10 26L17 22" stroke="#C4B5FD" strokeWidth="1.8" />
      </svg>
    );
  }

  // 12. Aider / OpenCode / GitHub Copilot
  if (id.includes('copilot') || id.includes('github')) {
    return (
      <svg width={size} height={size} viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path
          d="M12 14C12 11 15 9 20 9C25 9 28 11 28 14V24C28 27 25 29 20 29C15 29 12 27 12 24V14Z"
          fill="#6366F1"
          fillOpacity="0.25"
          stroke="#818CF8"
          strokeWidth="2"
        />
        <circle cx="16" cy="19" r="2.2" fill="#FFFFFF" />
        <circle cx="24" cy="19" r="2.2" fill="#FFFFFF" />
        <path d="M17 24H23" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" />
        <path d="M8 19H12M28 19H32" stroke="#818CF8" strokeWidth="2" strokeLinecap="round" />
      </svg>
    );
  }

  // 13. Kimi / Moonshot AI
  if (id.includes('kimi') || id.includes('moonshot')) {
    return (
      <svg width={size} height={size} viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path
          d="M26 20C26 25.5 21.5 30 16 30C12 30 8.5 27.5 7 24C8.2 24.3 9.4 24.5 10.7 24.5C16.2 24.5 20.7 20 20.7 14.5C20.7 13.2 20.5 12 20.2 10.8C23.7 12.3 26 15.8 26 20Z"
          fill="#F59E0B"
        />
        <circle cx="29" cy="13" r="2.5" fill="#FBBF24" />
      </svg>
    );
  }

  // 14. OpenRouter — Multi-Model Ray Routing Prism
  if (id.includes('openrouter') || id.includes('router')) {
    return (
      <svg width={size} height={size} viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <linearGradient id="orGrad" x1="6" y1="6" x2="34" y2="34" gradientUnits="userSpaceOnUse">
            <stop stopColor="#6366F1" />
            <stop offset="0.5" stopColor="#8B5CF6" />
            <stop offset="1" stopColor="#EC4899" />
          </linearGradient>
        </defs>
        {/* Hexagonal Prism Base */}
        <path
          d="M20 5L33 12.5V27.5L20 35L7 27.5V12.5L20 5Z"
          stroke="url(#orGrad)"
          strokeWidth="2.2"
          strokeLinejoin="round"
          fill="#6366F1"
          fillOpacity="0.12"
        />
        {/* Central Router Nexus */}
        <circle cx="20" cy="20" r="4" fill="url(#orGrad)" />
        {/* Route Rays */}
        <path d="M20 5V16M33 12.5L23.5 18M33 27.5L23.5 22M20 35V24M7 27.5L16.5 22M7 12.5L16.5 18" stroke="#A78BFA" strokeWidth="1.8" strokeLinecap="round" />
      </svg>
    );
  }

  // 15. Backboard.io (Espri.ai) — Sovereign AI Memory Grid & Adaptive Context Slate
  if (id.includes('backboard') || id.includes('espri')) {
    return (
      <svg width={size} height={size} viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <linearGradient id="bbGrad" x1="6" y1="6" x2="34" y2="34" gradientUnits="userSpaceOnUse">
            <stop stopColor="#10B981" />
            <stop offset="0.5" stopColor="#06B6D4" />
            <stop offset="1" stopColor="#3B82F6" />
          </linearGradient>
        </defs>
        {/* Memory Slate Frame */}
        <rect
          x="7"
          y="7"
          width="26"
          height="26"
          rx="5"
          stroke="url(#bbGrad)"
          strokeWidth="2.2"
          fill="#0F172A"
          fillOpacity="0.8"
        />
        {/* Persistent Memory Grid Interconnect */}
        <path d="M13 14H27M13 20H23M13 26H20" stroke="#38BDF8" strokeWidth="2" strokeLinecap="round" />
        <circle cx="25" cy="26" r="2.5" fill="#10B981" />
        <circle cx="27" cy="14" r="2" fill="#38BDF8" />
      </svg>
    );
  }

  // 16. Nebius Token Factory
  if (id.includes('nebius')) {
    return (
      <svg width={size} height={size} viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect x="8" y="8" width="24" height="24" rx="4" stroke="#00D2FF" strokeWidth="2" fill="#00D2FF" fillOpacity="0.1" />
        <path d="M14 26V14L26 26V14" stroke="#00D2FF" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }

  // Default fallback
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="20" cy="20" r="14" stroke="#60A5FA" strokeWidth="2" strokeDasharray="3 3" />
      <circle cx="20" cy="20" r="4" fill="#3B82F6" />
    </svg>
  );
};
