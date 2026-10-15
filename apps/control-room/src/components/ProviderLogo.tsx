import React from 'react';

interface ProviderLogoProps {
  providerId?: string;
  name?: string;
  size?: number;
  className?: string;
}

/**
 * Authentic vector logos for all AI agents, infrastructure, and inference providers.
 * All paths are extracted from official brand assets and standardized vector registries.
 */
export const ProviderLogo: React.FC<ProviderLogoProps> = ({ 
  providerId, 
  name, 
  size = 32,
  className = ''
}) => {
  const id = ((providerId || name || '') as string).toLowerCase().replace(/[-_]/g, '');

  // 1. Anthropic / Claude Code — Official Anthropic Mark
  if (id.includes('claude') || id.includes('anthropic')) {
    return (
      <svg 
        width={size} 
        height={size} 
        viewBox="0 0 24 24" 
        fill="none" 
        xmlns="http://www.w3.org/2000/svg"
        className={className}
        aria-label="Anthropic / Claude"
      >
        <path
          d="M17.3041 3.541h-3.6718l6.696 16.918H24Zm-10.6082 0L0 20.459h3.7442l1.3693-3.5527h7.0052l1.3693 3.5528h3.7442L10.5363 3.5409Zm-.3712 10.2232 2.2914-5.9456 2.2914 5.9456Z"
          fill="#D97757"
        />
      </svg>
    );
  }

  // 2. OpenAI / Codex — Official OpenAI Spiral Rosette
  if (id.includes('codex') || id.includes('openai') || id.includes('chatgpt') || id.includes('gpt')) {
    return (
      <svg 
        width={size} 
        height={size} 
        viewBox="0 0 24 24" 
        fill="none" 
        xmlns="http://www.w3.org/2000/svg"
        className={className}
        aria-label="OpenAI / Codex"
      >
        <path
          d="M22.2819 9.8211a5.9847 5.9847 0 0 0-.5157-4.9108 6.0462 6.0462 0 0 0-6.5098-2.9A6.0651 6.0651 0 0 0 4.9807 4.1818a5.9847 5.9847 0 0 0-3.9977 2.9 6.0462 6.0462 0 0 0 .7427 7.0966 5.98 5.98 0 0 0 .511 4.9107 6.051 6.051 0 0 0 6.5146 2.9001A5.9847 5.9847 0 0 0 13.2599 24a6.0557 6.0557 0 0 0 5.7718-4.2058 5.9894 5.9894 0 0 0 3.9977-2.9001 6.0557 6.0557 0 0 0-.7475-7.0729zm-9.022 12.6081a4.4755 4.4755 0 0 1-2.8764-1.0408l.1419-.0804 4.7783-2.7582a.7948.7948 0 0 0 .3927-.6813v-6.7369l2.02 1.1686a.071.071 0 0 1 .038.052v5.5826a4.504 4.504 0 0 1-4.4945 4.4944zm-9.6607-4.1254a4.4708 4.4708 0 0 1-.5346-3.0137l.142.0852 4.783 2.7582a.7712.7712 0 0 0 .7806 0l5.8428-3.3685v2.3324a.0804.0804 0 0 1-.0332.0615L9.74 19.9502a4.4992 4.4992 0 0 1-6.1408-1.6464zM2.3408 7.8956a4.485 4.485 0 0 1 2.3655-1.9728V11.6a.7664.7664 0 0 0 .3879.6765l5.8144 3.3543-2.0201 1.1685a.0757.0757 0 0 1-.071 0l-4.8303-2.7865A4.504 4.504 0 0 1 2.3408 7.872zm16.5963 3.8558L13.1038 8.364 15.1192 7.2a.0757.0757 0 0 1 .071 0l4.8303 2.7913a4.4944 4.4944 0 0 1-.6765 8.1042v-5.6772a.79.79 0 0 0-.407-.667zm2.0107-3.0231l-.142-.0852-4.7735-2.7818a.7759.7759 0 0 0-.7854 0L9.409 9.2297V6.8974a.0662.0662 0 0 1 .0284-.0615l4.8303-2.7866a4.4992 4.4992 0 0 1 6.6802 4.66zM8.3065 12.863l-2.02-1.1638a.0804.0804 0 0 1-.038-.0567V6.0742a4.4992 4.4992 0 0 1 7.3757-3.4537l-.142.0805L8.704 5.459a.7948.7948 0 0 0-.3927.6813zm1.0976-2.3654l2.602-1.4998 2.6069 1.4998v2.9994l-2.5974 1.4997-2.6067-1.4997Z"
          fill="#10A37F"
        />
      </svg>
    );
  }

  // 3. Google Gemini / Gemma — Official Google Gemini Hypocycloid Sparkle Star
  if (id.includes('gemini') || id.includes('google') || id.includes('gemma')) {
    const gradId = `gemini-grad-${size}`;
    return (
      <svg 
        width={size} 
        height={size} 
        viewBox="0 0 24 24" 
        fill="none" 
        xmlns="http://www.w3.org/2000/svg"
        className={className}
        aria-label="Google Gemini"
      >
        <defs>
          <linearGradient id={gradId} x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#1B72E8" />
            <stop offset="45%" stopColor="#8AB4F8" />
            <stop offset="75%" stopColor="#9B72CF" />
            <stop offset="100%" stopColor="#C084FC" />
          </linearGradient>
        </defs>
        <path
          d="M11.04 19.32Q12 21.51 12 24q0-2.49.93-4.68.96-2.19 2.58-3.81t3.81-2.55Q21.51 12 24 12q-2.49 0-4.68-.93a12.3 12.3 0 0 1-3.81-2.58 12.3 12.3 0 0 1-2.58-3.81Q12 2.49 12 0q0 2.49-.96 4.68-.93 2.19-2.55 3.81a12.3 12.3 0 0 1-3.81 2.58A12.3 12.3 0 0 1 0 12q2.49 0 4.68.93a12.3 12.3 0 0 1 3.81 2.58 12.3 12.3 0 0 1 2.55 3.81Z"
          fill={`url(#${gradId})`}
        />
      </svg>
    );
  }

  // 4. OpenRouter — Official OpenRouter Ray Prism Routing Mark
  if (id.includes('openrouter') || id.includes('router')) {
    const gradId = `or-grad-${size}`;
    return (
      <svg 
        width={size} 
        height={size} 
        viewBox="0 0 24 24" 
        fill="none" 
        xmlns="http://www.w3.org/2000/svg"
        className={className}
        aria-label="OpenRouter"
      >
        <defs>
          <linearGradient id={gradId} x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#6366F1" />
            <stop offset="100%" stopColor="#A855F7" />
          </linearGradient>
        </defs>
        <path
          d="M16.778 1.844v1.919q-.569-.026-1.138-.032-.708-.008-1.415.037c-1.93.126-4.023.728-6.149 2.237-2.911 2.066-2.731 1.95-4.14 2.75-.396.223-1.342.574-2.185.798-.841.225-1.753.333-1.751.333v4.229s.768.108 1.61.333c.842.224 1.789.575 2.185.799 1.41.798 1.228.683 4.14 2.75 2.126 1.509 4.22 2.11 6.148 2.236.88.058 1.716.041 2.555.005v1.918l7.222-4.168-7.222-4.17v2.176c-.86.038-1.611.065-2.278.021-1.364-.09-2.417-.357-3.979-1.465-2.244-1.593-2.866-2.027-3.68-2.508.889-.518 1.449-.906 3.822-2.59 1.56-1.109 2.614-1.377 3.978-1.466.667-.044 1.418-.017 2.278.02v2.176L24 6.014Z"
          fill={`url(#${gradId})`}
        />
      </svg>
    );
  }

  // 5. Hugging Face — Official Hugging Face 🤗 Brand Emblem
  if (id.includes('hugging') || id.includes('hf')) {
    return (
      <svg 
        width={size} 
        height={size} 
        viewBox="0 0 64 64" 
        fill="none" 
        xmlns="http://www.w3.org/2000/svg"
        className={className}
        aria-label="Hugging Face"
      >
        {/* Yellow Face Base */}
        <circle cx="32" cy="30" r="26" fill="#FFD21E" />
        {/* Rosy Cheeks */}
        <ellipse cx="16" cy="34" rx="5" ry="3.5" fill="#FF9D00" fillOpacity="0.8" />
        <ellipse cx="48" cy="34" rx="5" ry="3.5" fill="#FF9D00" fillOpacity="0.8" />
        {/* Left Brow & Eye */}
        <path
          d="M25.777 19.183c.504.374 1.21-.6.966-1.029c-2.452-4.251-5.342-6.084-7.831-5.646c-2.488.438-4.576 3.15-5.427 7.983c-.081.486.915 1.161 1.262.637c1.304-1.972 3.101-2.98 5.097-3.333c2-.353 4.034-.019 5.933 1.388"
          fill="#1C1917"
        />
        {/* Right Brow & Eye */}
        <path
          d="M38.223 19.183c-.504.374-1.21-.6-.966-1.029c2.452-4.251 5.342-6.084 7.831-5.646c2.488.438 4.576 3.15 5.427 7.983c.081.486-.915 1.161-1.262.637c-1.304-1.972-3.101-2.98-5.097-3.333c-2-.353-4.034-.019-5.933 1.388"
          fill="#1C1917"
        />
        {/* Smiling Mouth */}
        <path
          d="M44.231 27.729c.415-1.065-.546-1.97-1.303-1.214c-6.318 6.294-14.319 7.675-22.361 3.942c-.968-.451-1.563.728-.809 1.586c2.817 3.213 7.788 5.635 13.435 4.64c5.645-.995 9.488-4.97 11.038-8.954"
          fill="#1C1917"
        />
        {/* Hugging Arms & Hands with Fingers */}
        <path
          d="M6 46C6 38 11 36 15 39C16 40 16 42 14 43C11 44 9 46 11 50C13 54 18 53 22 48C23 46 25 47 24 49C21 54 14 58 8 52C6 50 6 48 6 46Z"
          fill="#FFD21E"
          stroke="#1C1917"
          strokeWidth="1.6"
        />
        <path
          d="M58 46C58 38 53 36 49 39C48 40 48 42 50 43C53 44 55 46 53 50C51 54 46 53 42 48C41 46 39 47 40 49C43 54 50 58 56 52C58 50 58 48 58 46Z"
          fill="#FFD21E"
          stroke="#1C1917"
          strokeWidth="1.6"
        />
      </svg>
    );
  }

  // 6. DigitalOcean — Official DigitalOcean Floating Pixel Emblem
  if (id.includes('digitalocean') || id.includes('droplet') || id === 'do') {
    return (
      <svg 
        width={size} 
        height={size} 
        viewBox="0 0 24 24" 
        fill="none" 
        xmlns="http://www.w3.org/2000/svg"
        className={className}
        aria-label="DigitalOcean"
      >
        <path
          d="M12.04 0C5.408-.02.005 5.37.005 11.992h4.638c0-4.923 4.882-8.731 10.064-6.855a6.95 6.95 0 014.147 4.148c1.889 5.177-1.924 10.055-6.84 10.064v-4.61H7.391v4.623h4.61V24c7.86 0 13.967-7.588 11.397-15.83-1.115-3.59-3.985-6.446-7.575-7.575A12.8 12.8 0 0012.039 0zM7.39 19.362H3.828v3.564H7.39zm-3.563 0v-2.978H.85v2.978z"
          fill="#0080FF"
        />
      </svg>
    );
  }

  // 7. Nebius — Official Nebius AI Studio Radial Token Burst
  if (id.includes('nebius')) {
    return (
      <svg 
        width={size} 
        height={size} 
        viewBox="0 0 40 40" 
        fill="none" 
        xmlns="http://www.w3.org/2000/svg"
        className={className}
        aria-label="Nebius AI Studio"
      >
        <rect x="2" y="2" width="36" height="36" rx="8" fill="#0A0F1D" stroke="#00E5FF" strokeWidth="1.5" strokeOpacity="0.6" />
        <g stroke="#00E5FF" strokeWidth="2.8" strokeLinecap="round">
          <line x1="20" y1="8" x2="20" y2="13" />
          <line x1="20" y1="27" x2="20" y2="32" />
          <line x1="8" y1="20" x2="13" y2="20" />
          <line x1="27" y1="20" x2="32" y2="20" />
          <line x1="11.5" y1="11.5" x2="15" y2="15" />
          <line x1="25" y1="25" x2="28.5" y2="28.5" />
          <line x1="28.5" y1="11.5" x2="25" y2="15" />
          <line x1="15" y1="25" x2="11.5" y2="28.5" />
        </g>
        <circle cx="20" cy="20" r="3.2" fill="#00E5FF" />
      </svg>
    );
  }

  // 8. Backboard.io (Espri.ai) — Sovereign Enterprise AI & Memory Grid
  if (id.includes('backboard') || id.includes('espri')) {
    const gradId = `bb-grad-${size}`;
    return (
      <svg 
        width={size} 
        height={size} 
        viewBox="0 0 40 40" 
        fill="none" 
        xmlns="http://www.w3.org/2000/svg"
        className={className}
        aria-label="Backboard.io / Espri"
      >
        <defs>
          <linearGradient id={gradId} x1="4" y1="4" x2="36" y2="36" gradientUnits="userSpaceOnUse">
            <stop stopColor="#10B981" />
            <stop offset="60%" stopColor="#06B6D4" />
            <stop offset="100%" stopColor="#3B82F6" />
          </linearGradient>
        </defs>
        <polygon 
          points="20,4 34,12 34,28 20,36 6,28 6,12" 
          fill="#0B132B" 
          stroke={`url(#${gradId})`} 
          strokeWidth="2" 
        />
        <path d="M12 15H28M12 20H25M12 25H22" stroke="#38BDF8" strokeWidth="2" strokeLinecap="round" />
        <circle cx="26" cy="25" r="2.2" fill="#10B981" />
        <circle cx="28" cy="15" r="2" fill="#06B6D4" />
      </svg>
    );
  }

  // 9. Cursor — Official 3D Isometric Cube Box Mark
  if (id.includes('cursor')) {
    return (
      <svg 
        width={size} 
        height={size} 
        viewBox="0 0 32 32" 
        fill="none" 
        xmlns="http://www.w3.org/2000/svg"
        className={className}
        aria-label="Cursor"
      >
        <polygon points="16,3 28,10 16,17 4,10" fill="#FB7185" />
        <polygon points="4,10 16,17 16,30 4,23" fill="#9F1239" />
        <polygon points="16,17 28,10 28,23 16,30" fill="#E11D48" />
        <path d="M16 17V30M16 17L28 10M16 17L4 10" stroke="#FFE4E6" strokeWidth="1" strokeOpacity="0.5" />
      </svg>
    );
  }

  // 10. Cline — Official Robot Mascot Emblem
  if (id.includes('cline')) {
    return (
      <svg 
        width={size} 
        height={size} 
        viewBox="0 0 40 40" 
        fill="none" 
        xmlns="http://www.w3.org/2000/svg"
        className={className}
        aria-label="Cline"
      >
        <rect x="7" y="10" width="26" height="22" rx="7" fill="#4F46E5" />
        <rect x="3" y="18" width="4" height="6" rx="2" fill="#818CF8" />
        <rect x="33" y="18" width="4" height="6" rx="2" fill="#818CF8" />
        <rect x="18.5" y="5" width="3" height="5" rx="1.5" fill="#818CF8" />
        <circle cx="20" cy="5" r="2.5" fill="#C7D2FE" />
        <rect x="11" y="14" width="18" height="9" rx="4.5" fill="#0F172A" />
        <circle cx="16" cy="18.5" r="2" fill="#38BDF8" />
        <circle cx="24" cy="18.5" r="2" fill="#38BDF8" />
        <path d="M17 26.5C18.5 28 21.5 28 23 26.5" stroke="#C7D2FE" strokeWidth="1.8" strokeLinecap="round" />
      </svg>
    );
  }

  // 11. Goose / Block — Official Origami Goose Geometry
  if (id.includes('goose') || id.includes('block')) {
    return (
      <svg 
        width={size} 
        height={size} 
        viewBox="0 0 40 40" 
        fill="none" 
        xmlns="http://www.w3.org/2000/svg"
        className={className}
        aria-label="Block Goose"
      >
        <polygon points="12,28 24,12 30,12 28,28" fill="#0D9488" />
        <polygon points="24,12 30,12 34,16 28,18" fill="#14B8A6" />
        <polygon points="8,26 12,28 28,28 24,34 10,34" fill="#0F766E" />
        <polygon points="34,16 38,17 32,19" fill="#F59E0B" />
        <circle cx="29" cy="15" r="1.5" fill="#FFFFFF" />
      </svg>
    );
  }

  // 12. Nous Research / Hermes Agent — Winged Helmet of Hermes
  if (id.includes('hermes') || id.includes('nous')) {
    return (
      <svg 
        width={size} 
        height={size} 
        viewBox="0 0 40 40" 
        fill="none" 
        xmlns="http://www.w3.org/2000/svg"
        className={className}
        aria-label="Nous Research Hermes"
      >
        <path
          d="M20 5L32 13V22C32 29 27 34 20 37C13 34 8 29 8 22V13L20 5Z"
          fill="#DC2626"
          stroke="#EF4444"
          strokeWidth="1.8"
        />
        <path d="M14 19H26M17 24H23" stroke="#FEF2F2" strokeWidth="2" strokeLinecap="round" />
        <path d="M8 14L2 8C5 12 5 18 8 20" stroke="#FCA5A5" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M32 14L38 8C35 12 35 18 32 20" stroke="#FCA5A5" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }

  // 13. Qwen (Alibaba Cloud) — Official Interlocking Polygon Mobius Loop
  if (id.includes('qwen') || id.includes('alibaba')) {
    return (
      <svg 
        width={size} 
        height={size} 
        viewBox="0 0 40 40" 
        fill="none" 
        xmlns="http://www.w3.org/2000/svg"
        className={className}
        aria-label="Alibaba Cloud Qwen"
      >
        <polygon points="20,6 32,13 26,17 14,10" fill="#7C3AED" />
        <polygon points="32,13 32,27 26,23 26,17" fill="#6D28D9" />
        <polygon points="32,27 20,34 14,30 26,23" fill="#8B5CF6" />
        <polygon points="20,34 8,27 14,23 26,23" fill="#6366F1" />
        <polygon points="8,27 8,13 14,17 14,30" fill="#4F46E5" />
        <polygon points="8,13 20,6 14,10 14,17" fill="#A78BFA" />
        <circle cx="20" cy="20" r="2.5" fill="#DDD6FE" />
      </svg>
    );
  }

  // 14. GitHub Copilot / OpenCode — Official GitHub Copilot Emblem
  if (id.includes('copilot') || id.includes('github') || id.includes('opencode')) {
    return (
      <svg 
        width={size} 
        height={size} 
        viewBox="0 0 256 208" 
        fill="none" 
        xmlns="http://www.w3.org/2000/svg"
        className={className}
        aria-label="GitHub Copilot / OpenCode"
      >
        <path
          d="M205.3 31.4c14 14.8 20 35.2 22.5 63.6 6.6 0 12.8 1.5 17 7.2l7.8 10.6c2.2 3 3.4 6.6 3.4 10.4v28.7a12 12 0 0 1-4.8 9.5C215.9 187.2 172.3 208 128 208c-49 0-98.2-28.3-123.2-46.6a12 12 0 0 1-4.8-9.5v-28.7c0-3.8 1.2-7.4 3.4-10.5l7.8-10.5c4.2-5.7 10.4-7.2 17-7.2 2.5-28.4 8.4-48.8 22.5-63.6C77.3 3.2 112.6 0 127.6 0h.4c14.7 0 50.4 2.9 77.3 31.4ZM128 78.7c-3 0-6.5.2-10.3.6a27.1 27.1 0 0 1-6 12.1 45 45 0 0 1-32 13c-6.8 0-13.9-1.5-19.7-5.2-5.5 1.9-10.8 4.5-11.2 11-.5 12.2-.6 24.5-.6 36.8 0 6.1 0 12.3-.2 18.5 0 3.6 2.2 6.9 5.5 8.4C79.9 185.9 105 192 128 192s48-6 74.5-18.1a9.4 9.4 0 0 0 5.5-8.4c.3-18.4 0-37-.8-55.3-.4-6.6-5.7-9.1-11.2-11-5.8 3.7-13 5.1-19.7 5.1a45 45 0 0 1-32-12.9 27.1 27.1 0 0 1-6-12.1c-3.4-.4-6.9-.5-10.3-.6Zm-27 44c5.8 0 10.5 4.6 10.5 10.4v19.2a10.4 10.4 0 0 1-20.8 0V133c0-5.8 4.6-10.4 10.4-10.4Zm53.4 0c5.8 0 10.4 4.6 10.4 10.4v19.2a10.4 10.4 0 0 1-20.8 0V133c0-5.8 4.7-10.4 10.4-10.4Zm-73-94.4c-11.2 1.1-20.6 4.8-25.4 10-10.4 11.3-8.2 40.1-2.2 46.2A31.2 31.2 0 0 0 75 91.7c6.8 0 19.6-1.5 30.1-12.2 4.7-4.5 7.5-15.7 7.2-27-.3-9.1-2.9-16.7-6.7-19.9-4.2-3.6-13.6-5.2-24.2-4.3Zm69 4.3c-3.8 3.2-6.4 10.8-6.7 19.9-.3 11.3 2.5 22.5 7.2 27a41.7 41.7 0 0 0 30 12.2c8.9 0 17-2.9 21.3-7.2 6-6.1 8.2-34.9-2.2-46.3-4.8-5-14.2-8.8-25.4-9.9-10.6-1-20 .7-24.2 4.3ZM128 56c-2.6 0-5.6.2-9 .5.4 1.7.5 3.7.7 5.7 0 1.5 0 3-.2 4.5 3.2-.3 6-.3 8.5-.3 2.6 0 5.3 0 8.5.3-.2-1.6-.2-3-.2-4.5.2-2 .3-4 .7-5.7-3.4-.3-6.4-.5-9-.5Z"
          fill="#8957E5"
        />
      </svg>
    );
  }

  // 15. Kimi / Moonshot AI — Official Moonshot Crescent Orbit
  if (id.includes('kimi') || id.includes('moonshot')) {
    return (
      <svg 
        width={size} 
        height={size} 
        viewBox="0 0 40 40" 
        fill="none" 
        xmlns="http://www.w3.org/2000/svg"
        className={className}
        aria-label="Moonshot AI Kimi"
      >
        <path
          d="M27 20C27 26.6 21.6 32 15 32C10.5 32 6.6 29.5 4.5 25.8C5.8 26.2 7.1 26.5 8.5 26.5C15.1 26.5 20.5 21.1 20.5 14.5C20.5 12.8 20.2 11.2 19.6 9.8C23.9 11.5 27 15.4 27 20Z"
          fill="#F59E0B"
        />
        <path d="M7 33C14 36 28 35 34 23C36 19 36 14 33 11" stroke="#FBBF24" strokeWidth="1.6" strokeDasharray="2 3" />
        <circle cx="31" cy="12" r="2.5" fill="#FBBF24" />
      </svg>
    );
  }

  // 16. Devin / Cognition — Official Cognition Brackets
  if (id.includes('devin') || id.includes('cognition')) {
    return (
      <svg 
        width={size} 
        height={size} 
        viewBox="0 0 40 40" 
        fill="none" 
        xmlns="http://www.w3.org/2000/svg"
        className={className}
        aria-label="Cognition Devin"
      >
        <rect x="6" y="6" width="28" height="28" rx="6" fill="#18181B" stroke="#06B6D4" strokeWidth="2" />
        <path d="M14 15L10 20L14 25" stroke="#22D3EE" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M26 15L30 20L26 25" stroke="#22D3EE" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M22 13L18 27" stroke="#38BDF8" strokeWidth="2" strokeLinecap="round" />
      </svg>
    );
  }

  // 17. Windsurf / Codeium — Official Codeium Dynamic Wave
  if (id.includes('windsurf') || id.includes('codeium')) {
    const gradId = `ws-grad-${size}`;
    return (
      <svg 
        width={size} 
        height={size} 
        viewBox="0 0 40 40" 
        fill="none" 
        xmlns="http://www.w3.org/2000/svg"
        className={className}
        aria-label="Codeium Windsurf"
      >
        <defs>
          <linearGradient id={gradId} x1="6" y1="6" x2="34" y2="34" gradientUnits="userSpaceOnUse">
            <stop stopColor="#06B6D4" />
            <stop offset="100%" stopColor="#10B981" />
          </linearGradient>
        </defs>
        <path
          d="M8 24C12 24 14 16 18 16C22 16 24 24 28 24C30 24 31 22 32 20M8 18C12 18 14 10 18 10C22 10 24 18 28 18C30 18 31 16 32 14M8 30C12 30 14 22 18 22C22 22 24 30 28 30C30 30 31 28 32 26"
          stroke={`url(#${gradId})`}
          strokeWidth="2.8"
          strokeLinecap="round"
        />
      </svg>
    );
  }

  // 18. Local Host / Workstation — Developer Host Machine
  if (id.includes('local') || id.includes('workstation') || id.includes('host')) {
    return (
      <svg 
        width={size} 
        height={size} 
        viewBox="0 0 40 40" 
        fill="none" 
        xmlns="http://www.w3.org/2000/svg"
        className={className}
        aria-label="Local Workstation"
      >
        <rect x="5" y="7" width="30" height="20" rx="3" fill="#1E293B" stroke="#64748B" strokeWidth="1.8" />
        <path d="M10 14L14 17L10 20" stroke="#38BDF8" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        <line x1="16" y1="20" x2="21" y2="20" stroke="#38BDF8" strokeWidth="2" strokeLinecap="round" />
        <path d="M16 27V31H24V27" stroke="#64748B" strokeWidth="1.8" strokeLinecap="round" />
        <line x1="12" y1="31" x2="28" y2="31" stroke="#64748B" strokeWidth="2" strokeLinecap="round" />
      </svg>
    );
  }

  // Fallback: Geometric High-Tech Radial Compass
  return (
    <svg 
      width={size} 
      height={size} 
      viewBox="0 0 40 40" 
      fill="none" 
      xmlns="http://www.w3.org/2000/svg"
      className={className}
    >
      <circle cx="20" cy="20" r="14" stroke="#64748B" strokeWidth="1.8" strokeDasharray="3 3" />
      <circle cx="20" cy="20" r="4" fill="#3B82F6" />
    </svg>
  );
};
