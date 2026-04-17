import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import type { PublicBrandingSettings } from '../api/types'
import {
  DEFAULT_BRAND_LOGO_SRC,
  DEFAULT_FAVICON_SRC,
  DEFAULT_SYSTEM_NAME,
} from '../config/brand'

export type BrandingState = {
  systemName: string
  logoSrc: string
  faviconSrc: string
  logoConfigured: boolean
  faviconConfigured: boolean
}

const defaultBranding: BrandingState = {
  systemName: DEFAULT_SYSTEM_NAME,
  logoSrc: DEFAULT_BRAND_LOGO_SRC,
  faviconSrc: DEFAULT_FAVICON_SRC,
  logoConfigured: false,
  faviconConfigured: false,
}

export function useBranding() {
  const query = useQuery({
    queryKey: ['settings', 'review', 'public-branding'],
    queryFn: async () => {
      const { data } = await api.get<PublicBrandingSettings>('/settings/review/public')
      return data
    },
    staleTime: 60_000,
  })

  const data = query.data
  const branding: BrandingState = {
    systemName: data?.system_name?.trim() || defaultBranding.systemName,
    logoSrc: data?.logo_url || defaultBranding.logoSrc,
    faviconSrc: data?.favicon_url || defaultBranding.faviconSrc,
    logoConfigured: data?.logo_configured ?? defaultBranding.logoConfigured,
    faviconConfigured: data?.favicon_configured ?? defaultBranding.faviconConfigured,
  }

  return { ...query, branding }
}
