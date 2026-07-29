FROM node:26-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json .npmrc ./
RUN npm ci

FROM node:26-alpine AS build
WORKDIR /app
ARG NEXT_PUBLIC_ODM_WS_URL=ws://127.0.0.1:8000/ws
ARG NEXT_PUBLIC_ODM_AVATAR_URL=/avatars/default.vrm
ARG NEXT_PUBLIC_ODM_RENDER_PRESET=stylized
ENV NEXT_PUBLIC_ODM_WS_URL=$NEXT_PUBLIC_ODM_WS_URL
ENV NEXT_PUBLIC_ODM_AVATAR_URL=$NEXT_PUBLIC_ODM_AVATAR_URL
ENV NEXT_PUBLIC_ODM_RENDER_PRESET=$NEXT_PUBLIC_ODM_RENDER_PRESET
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build
RUN npm prune --omit=dev

FROM node:26-alpine
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app/.next ./.next
COPY --from=build /app/public ./public
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/package.json ./package.json
USER node
EXPOSE 3000
CMD ["npm", "run", "start"]
