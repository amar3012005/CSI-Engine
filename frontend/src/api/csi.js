import service from './index'

export function getSimulationCsiState(simulationId) {
  return service.get(`/api/simulation/${simulationId}/csi/state`)
}

export function getSimulationCsiArtifacts(simulationId, params = {}) {
  return service.get(`/api/simulation/${simulationId}/csi/artifacts`, { params })
}

export function getSimulationCsiGraph(simulationId) {
  return service.get(`/api/simulation/${simulationId}/csi/graph`)
}
