# Thinking Trail: SceneForge Feature Sprint (July 2026)

PRs #77–#93 · 17 PRs merged · 192 tests · 82 endpoints

## Problem Framing

"at this pricing.. what could be the true benefit of SceneForge over Higgsfield? Can I still optimise the cost or do I get the benefit elsewhere?" — Higgsfield's enterprise ByteDance deal makes retail Seedance APIs more expensive per clip. The question was whether SceneForge has a structural edge beyond cost.

"think about all the features that SceneForge can provide to provide an edge and advantages over higgsfield alone.. think all whats possible technically, product wise and experience wise.. think deep." — Not a feature list, but a strategic differentiation analysis.

## Approach

"build an execution plan for all these features.. each step in the plan should be a claude code executable prompt.. then give me a loop prompt to execute." — 20-step execution plan, each step producing one branch → PR → merge cycle. Features ordered by dependency: prompt enhancement → shot types → smart routing → batch ops → AI Director → post-production → library/analytics.

"ammend the loop to merge the PR after CI/CD passes" — Loop evolved from open-PR-only to full merge-after-CI.

## Key Decisions

Multi-ref composition as the moat, not cost. "Character consistency via multi-ref composition. This is the actual differentiator. Higgsfield doesn't offer 8-14 reference image composition." Smart routing ("Auto" model per shot type) makes cost competitive without sacrificing quality on hero shots.

"demo should be behind /demo" — Demo mode was activating globally on Vercel (no backend → demo). Fixed to only activate at `/demo/*` routes. "what are you talking about.. I have been always using railway for the studio" — Vercel is not the Studio, Railway is.

"I removed the marketing page from vercel and moved it to railway as well" — Consolidated everything on Railway, eliminating Vercel as a deployment target.

## Pivots

Started with cost comparison (Higgsfield wins on Seedance pricing) → pivoted to workflow differentiation (AI Director, smart routing, multi-ref composition, batch operations). The pricing page was honest about the cost gap; the product strategy shifted to "workflow value > per-clip cost."

## Outcome

13 features shipped in one session: prompt enhancement, shot types, smart routing, draft→premium upgrade, batch scene/clip generation, full pipeline ("Produce"), AI Director, project templates, shot list generator, sequence builder, platform export, caption generation. Plus demo route fix, OG image, and README rewrite. 192 tests, 82 API endpoints, ~10K LOC.

---

<details>
<summary>Raw prompts (filtered)</summary>

1. "at this pricing.. what could be the true benefit of SceneForge over Higgsfield?"
2. "think about all the features that SceneForge can provide to provide an edge and advantages over higgsfield alone.. think deep"
3. "build an execution plan for all these features.. each step in the plan should be a claude code executable prompt.. then give me a loop prompt to execute"
4. `/loop` — Execute the next uncompleted step from EXECUTION_PLAN.md (repeated for steps 1-13)
5. "ammend the loop to merge the PR after CI/CD passes"
6. "I need a screenshot to use on linkedin and github"
7. "add to github sceneforge-og"
8. "still stuck at loading https://sceneforge-studio-three.vercel.app/"
9. "demo should be behind /demo"
10. "what are you talking about.. I have been always using railway for the studio"
11. "I removed the marketing page from vercel and moved it to railway as well"
12. "ok all good.. I was checking https://sceneforge-studio-three.vercel.app/"
13. "update repo readme"
14. "give me new landing page url"
15. "resolve conflicts on https://github.com/ahmedkhaledmohamed/SceneForge/pull/79"
16. "can't find site/screenshot.png"
17. "still can't find them"

</details>
