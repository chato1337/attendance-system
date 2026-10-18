# ADR-001: Gateway y Agente Edge como binarios separados

- Estado: aceptado
- Fecha: 2026-10-18

## Contexto

La especificación funcional pide validar accesos en el Edge en menos de 200 ms, incluso sin Internet. La guía del gateway, en cambio, deja esa validación en el navegador, que llama a la nube y luego ordena `open_door`. El gateway ya existe en otro repositorio y solo abstrae el puerto serial detrás de un WebSocket en `127.0.0.1:8080/ws`.

Fusionar el agente con el gateway acoplaría ese componente a este dominio. Dejar el navegador como puente incumple el requisito offline.

## Decisión

El gateway se conserva tal cual, como dependencia externa. No entra a este repositorio ni como copia ni como submódulo. El Agente Edge es un binario aparte que corre en la misma máquina, se conecta como cliente WebSocket, consume `hardware_read`, valida contra SQLite y envía `open_door`.

La integración se limita al contrato de `docs/hardware-gateway.md`. El agente documentará la versión del gateway con la que fue probado. Si el protocolo cambia, se actualiza esa guía, se adapta `edge/internal/gateway` y se anota en la bitácora. El simulador de gateway de la Fase 3 implementa el mismo contrato y es la referencia de las pruebas.

## Consecuencias

- El acceso local no depende del navegador ni de Internet.
- El gateway sigue siendo reutilizable y con su propio ciclo de versiones.
- El puerto del gateway permanece en loopback y sin autenticación, lo cual es aceptable solo porque el agente local es su único cliente.
- El panel web habla únicamente con la nube.
