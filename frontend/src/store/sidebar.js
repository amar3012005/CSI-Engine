import { ref } from 'vue'
import { safeGet, safeSet } from '../utils/safeStorage'

const sidebarCollapsed = ref(getInitialSidebarState())

function getInitialSidebarState() {
  return safeGet('sidebar_collapsed') === 'true'
}

export function useSidebar() {
  const toggleSidebar = () => {
    sidebarCollapsed.value = !sidebarCollapsed.value
    safeSet('sidebar_collapsed', sidebarCollapsed.value)
  }

  const collapseSidebar = () => {
    sidebarCollapsed.value = true
    safeSet('sidebar_collapsed', 'true')
  }

  const expandSidebar = () => {
    sidebarCollapsed.value = false
    safeSet('sidebar_collapsed', 'false')
  }

  return {
    sidebarCollapsed,
    toggleSidebar,
    collapseSidebar,
    expandSidebar
  }
}

