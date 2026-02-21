/**
 * FORESIGHT Auth Store (Zustand)
 *
 * Stores JWT token + tenant context with localStorage persistence.
 * The Axios interceptor reads from this store on every request.
 */

import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'

interface AuthStore {
  token: string | null
  tenantId: string | null
  isAuthenticated: boolean
  login: (token: string, tenantId: string) => void
  logout: () => void
}

export const useAuthStore = create<AuthStore>()(
  persist(
    (set) => ({
      token: null,
      tenantId: null,
      isAuthenticated: false,

      login: (token: string, tenantId: string) =>
        set({ token, tenantId, isAuthenticated: true }),

      logout: () =>
        set({ token: null, tenantId: null, isAuthenticated: false }),
    }),
    {
      name: 'foresight-auth',
      storage: createJSONStorage(() => localStorage),
    }
  )
)
