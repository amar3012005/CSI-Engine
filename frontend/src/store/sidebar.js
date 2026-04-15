import { ref } from 'vue'

const sidebarCollapsed = ref(getInitialSidebarState())

function getInitialSidebarState() {
  try {
    return localStorage.getItem('sidebar_collapsed') === 'true'
  } catch (e) {
    // Falls back to false if storage is disallowed (e.g. some iframe/privacy contexts)
    return false
  }
}

export function useSidebar() {
  const toggleSidebar = () => {
    sidebarCollapsed.value = !sidebarCollapsed.value
    try {
      localStorage.setItem('sidebar_collapsed', sidebarCollapsed.value)
    } catch (e) { /* ignore */ }
  }

  const collapseSidebar = () => {
    sidebarCollapsed.value = true
    try {
      localStorage.setItem('sidebar_collapsed', 'true')
    } catch (e) { /* ignore */ }
  }

  const expandSidebar = () => {
    sidebarCollapsed.value = false
    try {
      localStorage.setItem('sidebar_collapsed', 'false')
    } catch (e) { /* ignore */ }
  }

  return {
    sidebarCollapsed,
    toggleSidebar,
    collapseSidebar,
    expandSidebar
  }
}

