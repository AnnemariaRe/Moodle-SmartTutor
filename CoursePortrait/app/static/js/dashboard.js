const API_BASE = '/api/v1/courses';
let charts = {};
let coursesLoaded = false;
let dashboardData = {};

Chart.defaults.font.family = "'Inter', -apple-system, BlinkMacSystemFont, sans-serif";
Chart.defaults.color = '#5B7A99';

const pastelColors = {
    primary: 'rgba(118, 159, 205, 0.85)',
    secondary: 'rgba(123, 163, 168, 0.85)',
    success: 'rgba(140, 184, 159, 0.85)',
    warning: 'rgba(212, 165, 116, 0.85)',
    danger: 'rgba(201, 139, 139, 0.85)',
    blue: 'rgba(214, 230, 242, 0.9)',
    blueLight: 'rgba(232, 241, 248, 0.9)',
    sky: 'rgba(185, 215, 234, 0.9)',
    mint: 'rgba(212, 233, 226, 0.9)',
    peach: 'rgba(245, 230, 224, 0.9)',
};

const icons = {
    modules: '<i class="fas fa-book"></i>',
    bottleneck: '<i class="fas fa-exclamation-circle"></i>',
    students: '<i class="fas fa-users"></i>',
    retention: '<i class="fas fa-chart-line"></i>',
    check: '<i class="fas fa-check-circle"></i>',
    warning: '<i class="fas fa-exclamation-triangle"></i>',
    chart: '<i class="fas fa-chart-bar"></i>',
    video: '<i class="fas fa-film"></i>',
    lightbulb: '<i class="fas fa-lightbulb"></i>',
    error: '<i class="fas fa-times-circle"></i>',
};

const DEMO_DATA = (() => {
    const modules = [
        {
            moduleId: 101, sectionId: 1, step: 1,
            moduleName: 'Введение в Python', moduleType: 'page',
            studentCount: 15, avgDurationMs: 220000, watchPercent: 0.94,
            dropoutRate: 0.00, dropoutRisk: 0.06, difficultyScore: 0.14,
            difficultyLevel: 'easy', engagementScore: 0.94,
            difficultyDetails: {
                explanation: 'Страница: Лёгкий',
                metrics: [
                    { name: 'Время чтения', value: 420, normalizedValue: 0.15, weight: 0.35, contribution: 0.052, interpretation: 'Время чтения в норме' },
                    { name: 'Глубина прокрутки', value: 92, normalizedValue: 0.08, weight: 0.25, contribution: 0.020, interpretation: 'Большинство дочитывают' },
                    { name: 'Повторные посещения', value: 0.2, normalizedValue: 0.07, weight: 0.20, contribution: 0.013, interpretation: 'Читают один раз — материал понятен' },
                    { name: 'Отвал после страницы', value: 0, normalizedValue: 0.00, weight: 0.20, contribution: 0.000, interpretation: 'Низкий отвал' },
                ],
                suggestions: [],
            },
        },
        {
            moduleId: 102, sectionId: 1, step: 2,
            moduleName: 'Установка среды разработки', moduleType: 'resource',
            studentCount: 14, avgDurationMs: 380000, watchPercent: 0.87,
            dropoutRate: 0.07, dropoutRisk: 0.13, difficultyScore: 0.21,
            difficultyLevel: 'easy', engagementScore: 0.87,
            difficultyDetails: {
                explanation: 'Файл: Лёгкий',
                metrics: [
                    { name: 'Время в модуле', value: 380, normalizedValue: 0.19, weight: 0.40, contribution: 0.076, interpretation: 'Время в норме' },
                    { name: 'Отвал', value: 7, normalizedValue: 0.07, weight: 0.30, contribution: 0.021, interpretation: 'Низкий отвал' },
                    { name: 'Вовлечённость', value: 87, normalizedValue: 0.13, weight: 0.30, contribution: 0.039, interpretation: 'Высокая вовлечённость' },
                ],
                suggestions: [],
            },
        },
        {
            moduleId: 103, sectionId: 2, step: 3,
            moduleName: 'Переменные и типы данных', moduleType: 'page',
            studentCount: 13, avgDurationMs: 780000, watchPercent: 0.71,
            dropoutRate: 0.07, dropoutRisk: 0.30, difficultyScore: 0.37,
            difficultyLevel: 'easy', engagementScore: 0.71,
            difficultyDetails: {
                explanation: 'Страница: Лёгкий — время чтения немного выше нормы',
                metrics: [
                    { name: 'Время чтения', value: 780, normalizedValue: 0.43, weight: 0.35, contribution: 0.151, interpretation: 'Читают дольше ожидаемого' },
                    { name: 'Глубина прокрутки', value: 76, normalizedValue: 0.24, weight: 0.25, contribution: 0.060, interpretation: 'Часть не дочитывает' },
                    { name: 'Повторные посещения', value: 0.8, normalizedValue: 0.27, weight: 0.20, contribution: 0.053, interpretation: 'Иногда возвращаются' },
                    { name: 'Отвал после страницы', value: 7, normalizedValue: 0.07, weight: 0.20, contribution: 0.014, interpretation: 'Низкий отвал' },
                ],
                suggestions: ['Разбить на несколько страниц', 'Добавить иллюстрации и примеры'],
            },
        },
        {
            moduleId: 104, sectionId: 2, step: 4,
            moduleName: 'Условные операторы (тест)', moduleType: 'quiz',
            studentCount: 12, avgDurationMs: 680000, watchPercent: 0.65,
            dropoutRate: 0.08, dropoutRisk: 0.44, difficultyScore: 0.55,
            difficultyLevel: 'medium', engagementScore: 0.65,
            difficultyDetails: {
                explanation: 'Тест: Средний — средний балл ниже 70%, несколько попыток',
                metrics: [
                    { name: 'Средний балл', value: 61, normalizedValue: 0.39, weight: 0.35, contribution: 0.137, interpretation: 'Средний результат' },
                    { name: 'Среднее кол-во попыток', value: 2.4, normalizedValue: 0.70, weight: 0.25, contribution: 0.175, interpretation: 'Несколько попыток — требуется повторение' },
                    { name: 'Процент завершивших', value: 75, normalizedValue: 0.25, weight: 0.20, contribution: 0.050, interpretation: 'Большинство завершили тест' },
                    { name: 'Время выполнения', value: 680, normalizedValue: 0.76, weight: 0.20, contribution: 0.152, interpretation: 'Немного дольше ожидаемого' },
                ],
                suggestions: ['Упростить формулировки вопросов', 'Разбить тест на несколько меньших'],
            },
        },
        {
            moduleId: 105, sectionId: 3, step: 5,
            moduleName: 'Циклы и итерации (видео)', moduleType: 'video',
            studentCount: 10, avgDurationMs: 1140000, watchPercent: 0.38,
            dropoutRate: 0.17, dropoutRisk: 0.72, difficultyScore: 0.72,
            difficultyLevel: 'hard', engagementScore: 0.38,
            difficultyDetails: {
                explanation: 'Видео: Сложное — низкий просмотр (38%), много перемоток и пауз',
                metrics: [
                    { name: 'Процент просмотра', value: 38, normalizedValue: 0.62, weight: 0.30, contribution: 0.186, interpretation: 'Много не досматривают — возможно, слишком длинное' },
                    { name: 'Перемотки назад', value: 6, normalizedValue: 1.00, weight: 0.25, contribution: 0.250, interpretation: 'Много перемоток — сложные моменты' },
                    { name: 'Количество пауз', value: 9, normalizedValue: 0.90, weight: 0.20, contribution: 0.180, interpretation: 'Много пауз — требуется время на осмысление' },
                    { name: 'Отвал после видео', value: 17, normalizedValue: 0.17, weight: 0.25, contribution: 0.042, interpretation: 'Умеренный отвал' },
                ],
                suggestions: ['Сократить длительность видео', 'Разбить на несколько коротких видео', 'Добавить субтитры или конспект'],
            },
        },
        {
            moduleId: 106, sectionId: 3, step: 6,
            moduleName: 'Функции в Python (тест)', moduleType: 'quiz',
            studentCount: 7, avgDurationMs: 950000, watchPercent: 0.40,
            dropoutRate: 0.29, dropoutRisk: 0.81, difficultyScore: 0.74,
            difficultyLevel: 'hard', engagementScore: 0.40,
            difficultyDetails: {
                explanation: 'Тест: Сложный — низкий средний балл (41%), много попыток',
                metrics: [
                    { name: 'Средний балл', value: 41, normalizedValue: 0.59, weight: 0.35, contribution: 0.207, interpretation: 'Низкий результат — студенты испытывают трудности' },
                    { name: 'Среднее кол-во попыток', value: 3.1, normalizedValue: 1.00, weight: 0.25, contribution: 0.250, interpretation: 'Много попыток — материал сложный' },
                    { name: 'Процент завершивших', value: 57, normalizedValue: 0.43, weight: 0.20, contribution: 0.086, interpretation: 'Много незавершённых — возможно, слишком сложный' },
                    { name: 'Время выполнения', value: 950, normalizedValue: 1.00, weight: 0.20, contribution: 0.200, interpretation: 'Значительно дольше — вопросы сложные' },
                ],
                suggestions: ['Добавить обучающий материал перед тестом', 'Упростить формулировки вопросов', 'Разбить тест на несколько меньших'],
            },
        },
        {
            moduleId: 107, sectionId: 4, step: 7,
            moduleName: 'Работа со списками и словарями', moduleType: 'assign',
            studentCount: 6, avgDurationMs: 1560000, watchPercent: 0.62,
            dropoutRate: 0.14, dropoutRisk: 0.55, difficultyScore: 0.46,
            difficultyLevel: 'medium', engagementScore: 0.62,
            difficultyDetails: {
                explanation: 'Задание: Среднее — часть студентов сдала с опозданием',
                metrics: [
                    { name: 'Процент сдавших', value: 67, normalizedValue: 0.33, weight: 0.30, contribution: 0.099, interpretation: 'Часть не сдала' },
                    { name: 'Средняя оценка', value: 62, normalizedValue: 0.38, weight: 0.30, contribution: 0.114, interpretation: 'Средние оценки' },
                    { name: 'Сдали с опозданием', value: 33, normalizedValue: 0.33, weight: 0.20, contribution: 0.066, interpretation: 'Умеренное количество опозданий' },
                    { name: 'Пересдачи', value: 17, normalizedValue: 0.34, weight: 0.20, contribution: 0.068, interpretation: 'Умеренное количество пересдач' },
                ],
                suggestions: ['Добавить примеры выполнения', 'Добавить промежуточную обратную связь'],
            },
        },
        {
            moduleId: 108, sectionId: 4, step: 8,
            moduleName: 'Итоговый проект', moduleType: 'assign',
            studentCount: 4, avgDurationMs: 5400000, watchPercent: 0.52,
            dropoutRate: 0.33, dropoutRisk: 0.63, difficultyScore: 0.50,
            difficultyLevel: 'medium', engagementScore: 0.52,
            difficultyDetails: {
                explanation: 'Задание: Среднее — много опозданий, низкие оценки',
                metrics: [
                    { name: 'Процент сдавших', value: 75, normalizedValue: 0.25, weight: 0.30, contribution: 0.075, interpretation: 'Большинство сдали' },
                    { name: 'Средняя оценка', value: 52, normalizedValue: 0.48, weight: 0.30, contribution: 0.144, interpretation: 'Средние оценки' },
                    { name: 'Сдали с опозданием', value: 50, normalizedValue: 0.50, weight: 0.20, contribution: 0.100, interpretation: 'Много опозданий — недостаточно времени' },
                    { name: 'Пересдачи', value: 25, normalizedValue: 0.50, weight: 0.20, contribution: 0.100, interpretation: 'Умеренное количество пересдач' },
                ],
                suggestions: ['Увеличить срок выполнения', 'Разбить на несколько этапов', 'Добавить чек-лист требований'],
            },
        },
    ];

    const heatmap = {
        courseId: 0,
        totalModules: modules.length,
        bottleneckModules: [105, 106],
        generatedAt: new Date().toISOString(),
        modules,
    };

    const funnel = {
        courseId: 0,
        totalStudents: 15,
        finalRetentionRate: 0.27,
        backwardNavigationRate: 0.18,
        avgCourseCompletionTimeMs: 18720000,
        avgSessionsPerUser: 6.3,
        funnel: modules.map(m => ({
            step: m.step,
            moduleId: m.moduleId,
            moduleName: m.moduleName,
            studentsCount: m.studentCount,
            retentionRate: parseFloat((m.studentCount / 15).toFixed(2)),
        })),
    };

    const dropoff = {
        courseId: 0,
        totalEnrolled: 15,
        totalStarted: 15,
        totalCompleted: 4,
        topDropoffChains: [[104, 105, 106], [103, 104, 105]],
        methodologyExplanation: 'Процент отвала показывает долю студентов, которые открыли модуль, но не перешли к следующим модулям курса.',
        dropoffPoints: [
            {
                moduleId: 106, moduleName: 'Функции в Python (тест)', moduleType: 'quiz', step: 6,
                studentsEntered: 7, studentsDropped: 4, studentsContinued: 3,
                dropoutRate: 0.57, avgTimeBeforeDropout: 1850000,
            },
            {
                moduleId: 108, moduleName: 'Итоговый проект', moduleType: 'assign', step: 8,
                studentsEntered: 4, studentsDropped: 2, studentsContinued: 2,
                dropoutRate: 0.50, avgTimeBeforeDropout: 3200000,
            },
            {
                moduleId: 105, moduleName: 'Циклы и итерации (видео)', moduleType: 'video', step: 5,
                studentsEntered: 10, studentsDropped: 4, studentsContinued: 6,
                dropoutRate: 0.40, avgTimeBeforeDropout: 920000,
            },
        ],
    };

    const video = {
        courseId: 0,
        totalVideos: 1,
        videos: [{
            courseId: 0,
            moduleId: 105,
            moduleName: 'Циклы и итерации (видео)',
            mediaId: '/course/video/lecture_loops_python.mp4',
            mediaType: 'video',
            videoDurationMs: 1320000,
            uniqueUsers: 10,
            avgWatchPercent: 52,
            avgFinalPercent: 45,
            avgTotalWatchTime: 686000,
            pauseCount: 38,
            seekCount: 24,
            seekBackwardCount: 18,
            segments: [
                { segment: '0-25',  avgWatchTime: 300000, segmentDuration: 330000, watchPercent: 91, watchShare: 0.35, pauseCount: 6,  isWellWatched: true,  isLeastWatched: false },
                { segment: '25-50', avgWatchTime: 241000, segmentDuration: 330000, watchPercent: 73, watchShare: 0.28, pauseCount: 12, isWellWatched: false, isLeastWatched: false },
                { segment: '50-75', avgWatchTime: 139000, segmentDuration: 330000, watchPercent: 42, watchShare: 0.22, pauseCount: 15, isWellWatched: false, isLeastWatched: false },
                { segment: '75-100',avgWatchTime:  92000, segmentDuration: 330000, watchPercent: 28, watchShare: 0.15, pauseCount: 5,  isWellWatched: false, isLeastWatched: true  },
            ],
            pauseHotspots: [
                { segment: '50-75', pauseCount: 15, avgPauseTime: 18000 },
                { segment: '25-50', pauseCount: 12, avgPauseTime: 12000 },
                { segment: '0-25',  pauseCount:  6, avgPauseTime:  8000 },
            ],
            seekPatterns: [
                { fromSegment: '50-75', toSegment: '25-50', avgFromTimeMs: 660000, avgToTimeMs: 330000, isBackward: true,  count: 12 },
                { fromSegment: '75-100',toSegment: '50-75', avgFromTimeMs: 990000, avgToTimeMs: 660000, isBackward: true,  count:  8 },
                { fromSegment: '25-50', toSegment: '50-75', avgFromTimeMs: 330000, avgToTimeMs: 660000, isBackward: false, count:  4 },
            ],
        }],
    };

    const recommendations = {
        courseId: 0,
        recommendations: [
            {
                moduleId: 106, moduleName: 'Функции в Python (тест)',
                issue: 'High dropout (57%); High difficulty (score: 0.74)',
                recommendation: 'Add intermediate quizzes to check understanding | Simplify content or break into smaller parts',
                priority: 'high',
            },
            {
                moduleId: 105, moduleName: 'Циклы и итерации (видео)',
                issue: 'High dropout (40%); Low watch rate (38%)',
                recommendation: 'Simplify content or break into smaller parts | Review module duration and structure',
                priority: 'high',
            },
            {
                moduleId: 108, moduleName: 'Итоговый проект',
                issue: 'High dropout (50%)',
                recommendation: 'Add intermediate quizzes to check understanding | Provide supplementary learning materials',
                priority: 'high',
            },
            {
                moduleId: 107, moduleName: 'Работа со списками и словарями',
                issue: 'High difficulty (score: 0.46)',
                recommendation: 'Add additional explanations and examples | Provide supplementary learning materials',
                priority: 'medium',
            },
            {
                moduleId: 104, moduleName: 'Условные операторы (тест)',
                issue: 'High difficulty (score: 0.55)',
                recommendation: 'Add additional explanations and examples',
                priority: 'medium',
            },
        ],
    };

    const courseInfo = { courseId: 0, courseName: 'Основы программирования на Python' };

    return { courseInfo, heatmap, funnel, dropoff, video, recommendations };
})();

document.addEventListener('DOMContentLoaded', () => {
    const today = new Date();
    const monthAgo = new Date();
    monthAgo.setDate(today.getDate() - 30);

    document.getElementById('dateTo').value = today.toISOString().split('T')[0];
    document.getElementById('dateFrom').value = monthAgo.toISOString().split('T')[0];

    loadCoursesList();
});

/**
 * Загрузка списка курсов из Moodle
 */
async function loadCoursesList() {
    const select = document.getElementById('courseSelect');

    const addDemoOption = () => {
        const demo = document.createElement('option');
        demo.value = 'demo';
        demo.textContent = 'Демо: Основы программирования на Python';
        demo.style.fontWeight = '600';
        demo.style.color = '#4a7fbf';
        select.appendChild(demo);
    };

    select.innerHTML = '<option value="">— Выберите курс —</option>';
    addDemoOption();

    try {
        const response = await fetch(API_BASE);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();

        if (data.courses && data.courses.length > 0) {
            const sep = document.createElement('option');
            sep.disabled = true;
            sep.textContent = '──────────────────';
            select.appendChild(sep);

            data.courses.forEach(course => {
                const option = document.createElement('option');
                option.value = course.id;
                option.textContent = course.fullname + (course.shortname ? ` (${course.shortname})` : '');
                select.appendChild(option);
            });
            coursesLoaded = true;
        }
    } catch (error) {
        console.warn('Курсы Moodle недоступны, только демо-режим:', error.message);
    }
}

/**
 * Обработчик выбора курса из списка
 */
function onCourseSelect() {
    const select = document.getElementById('courseSelect');
    if (select.value) {
        loadDashboard();
    }
}

/**
 * Получить выбранный ID курса
 */
function getSelectedCourseId() {
    return document.getElementById('courseSelect').value;
}

/**
 * Показать сообщение об ошибке
 */
function showError(message) {
    const container = document.getElementById('errorContainer');
    container.innerHTML = `<div class="error">${icons.error} ${message}</div>`;
}

/**
 * Очистить сообщения об ошибках
 */
function clearError() {
    document.getElementById('errorContainer').innerHTML = '';
}

/**
 * Переключение между вкладками
 */
function switchTab(tabName) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    event.target.closest('.tab').classList.add('active');
    document.getElementById(tabName).classList.add('active');
    
    setTimeout(() => {
        Object.values(charts).forEach(chart => {
            if (chart && typeof chart.resize === 'function') {
                chart.resize();
            }
        });
    }, 100);
}

/**
 * Загрузка всех данных дашборда
 */
async function loadDashboard() {
    clearError();
    const courseId = getSelectedCourseId();
    const dateFrom = document.getElementById('dateFrom').value;
    const dateTo = document.getElementById('dateTo').value;

    if (!courseId) {
        showError('Выберите курс из списка');
        return;
    }

    document.getElementById('loading').style.display = 'block';
    document.getElementById('dashboard').style.display = 'none';

    // ----- DEMO MODE -----
    if (courseId === 'demo') {
        const { courseInfo, heatmap, dropoff, funnel, video, recommendations } = DEMO_DATA;
        dashboardData = { courseInfo, heatmap, dropoff, funnel, video, recommendations };
        document.getElementById('loading').style.display = 'none';
        document.getElementById('dashboard').style.display = 'block';
        document.querySelector('.header h1').innerHTML =
            `<i class="fas fa-chart-pie"></i> ${courseInfo.courseName} <span style="font-size:0.6em;background:#e8f0fa;color:#4a7fbf;padding:2px 8px;border-radius:12px;vertical-align:middle;font-weight:600;">DEMO</span>`;
        renderOverview(heatmap, dropoff, funnel);
        renderAnalytics(heatmap, dropoff);
        renderMedia(video, recommendations);
        return;
    }
    // ----- END DEMO MODE -----

    try {
        const [courseInfo, heatmap, dropoff, funnel, video, recommendations] = await Promise.all([
            fetch(`${API_BASE}/${courseId}/info`).then(r => r.json()).catch(() => null),
            fetch(`${API_BASE}/${courseId}/heatmap?date_from=${dateFrom}&date_to=${dateTo}`).then(r => r.json()).catch(() => null),
            fetch(`${API_BASE}/${courseId}/dropoff-points`).then(r => r.json()).catch(() => null),
            fetch(`${API_BASE}/${courseId}/funnel?date_from=${dateFrom}&date_to=${dateTo}`).then(r => r.json()).catch(() => null),
            fetch(`${API_BASE}/${courseId}/video-analytics?date_from=${dateFrom}&date_to=${dateTo}`).then(r => r.json()).catch(() => null),
            fetch(`${API_BASE}/${courseId}/recommendations`).then(r => r.json()).catch(() => null),
        ]);

        dashboardData = { courseInfo, heatmap, dropoff, funnel, video, recommendations };

        document.getElementById('loading').style.display = 'none';
        document.getElementById('dashboard').style.display = 'block';

        if (courseInfo && courseInfo.courseName) {
            document.querySelector('.header h1').innerHTML = `<i class="fas fa-chart-pie"></i> ${courseInfo.courseName}`;
        }

        renderOverview(heatmap, dropoff, funnel);
        renderAnalytics(heatmap, dropoff);
        renderMedia(video, recommendations);

    } catch (error) {
        document.getElementById('loading').style.display = 'none';
        showError(`Ошибка загрузки данных: ${error.message}`);
    }
}

/**
 * Рендеринг вкладки "Обзор" - статистика, воронка и узкие места
 */
function renderOverview(heatmap, dropoff, funnel) {
    const stats = [
        { label: 'Всего модулей', value: heatmap?.totalModules || 0, icon: icons.modules },
        { label: 'Узких мест', value: heatmap?.bottleneckModules?.length || 0, icon: icons.bottleneck },
        { label: 'Всего студентов', value: funnel?.totalStudents || 0, icon: icons.students },
        { label: 'Удержание', value: funnel ? `${(funnel.finalRetentionRate * 100).toFixed(0)}%` : 'N/A', icon: icons.retention },
    ];

    document.getElementById('statsGrid').innerHTML = stats.map(s => `
        <div class="stat-card">
            <h3>${s.icon} ${s.label}</h3>
            <div class="value">${s.value}</div>
        </div>
    `).join('');

    renderFunnelChart(funnel);

    if (funnel) {
        const funnelStatsHtml = `
            <div class="funnel-stats" style="display: flex; gap: 12px; margin-bottom: 12px; flex-wrap: wrap;">
                <div class="stat-mini" style="flex: 1; min-width: 140px; background: var(--bg-light, #f8f9fa); border-radius: 8px; padding: 10px 12px;">
                    <div style="font-size: 0.8em; color: #666;"><i class="fas fa-undo"></i> Возвраты назад</div>
                    <div style="font-size: 1.1em; font-weight: 600;">${(funnel.backwardNavigationRate * 100).toFixed(0)}%</div>
                </div>
                <div class="stat-mini" style="flex: 1; min-width: 140px; background: var(--bg-light, #f8f9fa); border-radius: 8px; padding: 10px 12px;">
                    <div style="font-size: 0.8em; color: #666;"><i class="fas fa-hourglass-half"></i> Ср. время в курсе</div>
                    <div style="font-size: 1.1em; font-weight: 600;">${formatDuration(funnel.avgCourseCompletionTimeMs)}</div>
                </div>
                <div class="stat-mini" style="flex: 1; min-width: 140px; background: var(--bg-light, #f8f9fa); border-radius: 8px; padding: 10px 12px;">
                    <div style="font-size: 0.8em; color: #666;"><i class="fas fa-redo"></i> Ср. число сессий</div>
                    <div style="font-size: 1.1em; font-weight: 600;">${funnel.avgSessionsPerUser.toFixed(1)}</div>
                </div>
            </div>
        `;

        const stepsHtml = funnel.funnel ? funnel.funnel.slice(0, 6).map(s => `
            <div class="module-item">
                <div>
                    <strong>${s.moduleName || `Модуль ${s.moduleId}`}</strong>
                    <div class="meta">Шаг ${s.step} • Удержание: ${(s.retentionRate * 100).toFixed(0)}%</div>
                </div>
                <span class="badge badge-info">${s.studentsCount}</span>
            </div>
        `).join('') : '';

        document.getElementById('funnelSteps').innerHTML = funnelStatsHtml + stepsHtml;
    }

    if (heatmap?.bottleneckModules && heatmap.bottleneckModules.length > 0) {
        const bottlenecks = heatmap.modules.filter(m => heatmap.bottleneckModules.includes(m.moduleId));
        document.getElementById('bottlenecksList').innerHTML = bottlenecks.map((m, idx) => {
            const typeIcon = getModuleTypeIcon(m.moduleType || 'unknown');
            const typeName = getModuleTypeName(m.moduleType || 'unknown');
            const hasDetails = m.difficultyDetails && m.difficultyDetails.metrics;
            const detailsId = `bottleneck-details-${idx}`;

            const metricsItems = [
                `<span><i class="fas fa-chart-bar"></i> Сложность: <strong>${m.difficultyScore.toFixed(2)}</strong></span>`,
                `<span><i class="fas fa-users"></i> Студентов: <strong>${m.studentCount}</strong></span>`,
                `<span><i class="fas fa-clock"></i> Ср. время: <strong>${formatDuration(m.avgDurationMs)}</strong></span>`,
            ];
            console.log(`dropoutRisk: ${m.dropoutRisk}, dropoutrate: ${m.dropoutRate}`);
            if (m.dropoutRate.toFixed(0) > 0) {
                metricsItems.push(`<span><i class="fas fa-sign-out-alt"></i> Отвал: <strong>${(m.dropoutRate * 100).toFixed(0)}%</strong></span>`);
            }
            if (m.dropoutRisk.toFixed(0) > 0) {
                metricsItems.push(`<span><i class="fas fa-brain"></i> ML риск отвала: <strong>${(m.dropoutRisk * 100).toFixed(0)}%</strong></span>`);
            }

            const detailsHtml = hasDetails ? renderDifficultyDetails(m.difficultyDetails) : '';

            return `
                <div class="module-item bottleneck">
                    <div style="flex: 1;">
                        <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 6px;">
                            ${typeIcon}
                            <strong>${m.moduleName || `Модуль ${m.moduleId}`}</strong>
                            <span class="badge badge-secondary" style="font-size: 0.75em;">${typeName}</span>
                            <span class="badge badge-danger">Узкое место</span>
                        </div>
                        <div class="bottleneck-metrics">
                            ${metricsItems.join('')}
                        </div>
                        ${hasDetails ? `
                            <div class="bottleneck-details-toggle" onclick="toggleDifficultyDetails('${detailsId}')" style="cursor: pointer; margin-top: 6px; color: var(--primary-color); font-size: 0.85em;">
                                <i class="fas fa-info-circle"></i> Подробнее о сложности
                            </div>
                            <div id="${detailsId}" style="display: none; margin-top: 8px;">
                                ${detailsHtml}
                            </div>
                        ` : ''}
                    </div>
                </div>
            `;
        }).join('');
    } else {
        document.getElementById('bottlenecksList').innerHTML = `
            <div class="empty-state">
                <div class="icon">${icons.check}</div>
                <p>Узких мест не обнаружено</p>
            </div>
        `;
    }
}

/**
 * Рендеринг графика воронки
 */
function renderFunnelChart(funnel) {
    if (!funnel) return;

    const ctx = document.getElementById('funnelChart');
    if (charts.funnel) charts.funnel.destroy();

    const gradient = ctx.getContext('2d').createLinearGradient(0, 0, 0, 240);
    gradient.addColorStop(0, 'rgba(118, 159, 205, 0.4)');
    gradient.addColorStop(1, 'rgba(185, 215, 234, 0.1)');

    charts.funnel = new Chart(ctx, {
        type: 'line',
        data: {
            labels: funnel.funnel.map(s => s.moduleName || `Шаг ${s.step}`),
            datasets: [{
                label: 'Студенты',
                data: funnel.funnel.map(s => s.studentsCount),
                borderColor: pastelColors.primary,
                backgroundColor: gradient,
                fill: true,
                tension: 0.4,
                pointBackgroundColor: pastelColors.primary,
                pointBorderColor: '#fff',
                pointBorderWidth: 2,
                pointRadius: 4,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false }
            },
            scales: {
                y: { 
                    beginAtZero: true,
                    grid: { color: 'rgba(118, 159, 205, 0.1)' },
                    title: {
                        display: true,
                        text: 'Студенты',
                        color: '#5B7A99',
                        font: { weight: '600' }
                    }
                },
                x: {
                    grid: { display: false },
                    ticks: { maxRotation: 45, minRotation: 45 }
                }
            },
            animation: false
        }
    });
}

/**
 * Рендеринг вкладки "Аналитика" - heatmap и dropoff в 2x2 сетке
 */
function renderAnalytics(heatmap, dropoff) {
    renderHeatmapChart(heatmap);
    renderDropoffChart(heatmap);
    renderDistributionChart(heatmap);
    renderModulesList(heatmap);
    renderDropoffPoints(dropoff);
}

/**
 * Рендеринг графика сложности (Heatmap)
 */
function renderHeatmapChart(heatmap) {
    if (!heatmap) return;

    const ctx = document.getElementById('heatmapChart');
    if (charts.heatmap) charts.heatmap.destroy();
    
    charts.heatmap = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: heatmap.modules.map(m => m.moduleName?.substring(0, 30) || `М${m.moduleId}`),
            datasets: [{
                label: 'Сложность',
                data: heatmap.modules.map(m => m.difficultyScore),
                backgroundColor: heatmap.modules.map(m => {
                    if (m.difficultyScore >= 0.6) return pastelColors.danger;
                    if (m.difficultyScore >= 0.3) return pastelColors.warning;
                    return pastelColors.success;
                }),
                borderRadius: 4,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false }
            },
            scales: {
                y: { 
                    beginAtZero: true, 
                    max: 1,
                    grid: { color: 'rgba(118, 159, 205, 0.1)' }
                },
                x: {
                    grid: { display: false },
                    ticks: { maxRotation: 45, minRotation: 45, font: { size: 10 } }
                }
            },
            animation: false
        }
    });
}

/**
 * Рендеринг графика точек отвала
 */
function renderDropoffChart(heatmap) {
    if (!heatmap || !heatmap.modules) return;

    const modules = heatmap.modules
        .filter(m => m.dropoutRate > 0)
        .sort((a, b) => (a.step || 0) - (b.step || 0));

    if (modules.length === 0) return;

    const ctx = document.getElementById('dropoffChart');
    if (charts.dropoff) charts.dropoff.destroy();

    charts.dropoff = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: modules.map(m => m.moduleName?.substring(0, 30) || `М${m.moduleId}`),
            datasets: [{
                label: 'Отвал %',
                data: modules.map(m => m.dropoutRate * 100),
                backgroundColor: modules.map(m => {
                    const rate = m.dropoutRate;
                    if (rate >= 0.5) return pastelColors.danger;
                    if (rate >= 0.2) return pastelColors.warning;
                    return pastelColors.success;
                }),
                borderRadius: 4,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    max: 100,
                    grid: { color: 'rgba(118, 159, 205, 0.1)' }
                },
                x: {
                    grid: { display: false },
                    ticks: { maxRotation: 80, minRotation: 80, font: { size: 10 } }
                }
            },
            animation: false
        }
    });
}

/**
 * Рендеринг графика распределения сложности
 */
function renderDistributionChart(heatmap) {
    if (!heatmap) return;

    const ctx = document.getElementById('distributionChart');
    if (charts.distribution) charts.distribution.destroy();

    const easy = heatmap.modules.filter(m => m.difficultyScore < 0.3).length;
    const medium = heatmap.modules.filter(m => m.difficultyScore >= 0.3 && m.difficultyScore < 0.6).length;
    const hard = heatmap.modules.filter(m => m.difficultyScore >= 0.6).length;

    charts.distribution = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Легкие', 'Средние', 'Сложные'],
            datasets: [{
                data: [easy, medium, hard],
                backgroundColor: [pastelColors.success, pastelColors.warning, pastelColors.danger],
                borderWidth: 0,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'right',
                    labels: {
                        padding: 10,
                        usePointStyle: true,
                        pointStyle: 'circle',
                        font: { size: 11 }
                    }
                }
            },
            cutout: '55%',
            animation: false
        }
    });
}

/**
 * Получить иконку для типа модуля
 */
function getModuleTypeIcon(moduleType) {
    const typeIcons = {
        'page': '<i class="fas fa-file-alt"></i>',
        'quiz': '<i class="fas fa-question-circle"></i>',
        'resource': '<i class="fas fa-file-download"></i>',
        'url': '<i class="fas fa-link"></i>',
        'forum': '<i class="fas fa-comments"></i>',
        'assign': '<i class="fas fa-tasks"></i>',
        'video': '<i class="fas fa-film"></i>',
        'label': '<i class="fas fa-tag"></i>',
        'folder': '<i class="fas fa-folder"></i>',
        'book': '<i class="fas fa-book-open"></i>',
        'lesson': '<i class="fas fa-graduation-cap"></i>',
        'workshop': '<i class="fas fa-users-cog"></i>',
        'glossary': '<i class="fas fa-spell-check"></i>',
        'wiki': '<i class="fas fa-wikipedia-w"></i>',
        'chat': '<i class="fas fa-comment-dots"></i>',
        'choice': '<i class="fas fa-poll"></i>',
        'feedback': '<i class="fas fa-clipboard-list"></i>',
        'survey': '<i class="fas fa-chart-bar"></i>',
        'scorm': '<i class="fas fa-cube"></i>',
        'h5pactivity': '<i class="fas fa-puzzle-piece"></i>',
        'lti': '<i class="fas fa-external-link-alt"></i>',
        'data': '<i class="fas fa-database"></i>',
        'unknown': '<i class="fas fa-question"></i>'
    };
    return typeIcons[moduleType] || typeIcons['unknown'];
}

/**
 * Получить человекочитаемое название типа модуля
 */
function getModuleTypeName(moduleType) {
    const typeNames = {
        'page': 'Страница',
        'quiz': 'Тест',
        'resource': 'Файл',
        'url': 'Ссылка',
        'forum': 'Форум',
        'assign': 'Задание',
        'video': 'Видео',
        'label': 'Метка',
        'folder': 'Папка',
        'book': 'Книга',
        'lesson': 'Лекция',
        'workshop': 'Семинар',
        'glossary': 'Глоссарий',
        'wiki': 'Вики',
        'chat': 'Чат',
        'choice': 'Опрос',
        'feedback': 'Обратная связь',
        'survey': 'Анкета',
        'scorm': 'SCORM',
        'h5pactivity': 'H5P',
        'lti': 'Внешний инструмент',
        'data': 'База данных',
        'unknown': 'Неизвестно'
    };
    return typeNames[moduleType] || moduleType || 'Неизвестно';
}

/**
 * Генерация HTML для детализации сложности (tooltip)
 */
function formatMetricValue(name, value) {
    if (typeof value !== 'number') return value;
    const timeNames = ['время', 'time'];
    const isTime = timeNames.some(t => name.toLowerCase().includes(t));
    if (isTime && value > 10) return formatDuration(value * 1000);
    return value % 1 === 0 ? value.toString() : value.toFixed(1);
}

function renderDifficultyDetails(details) {
    if (!details || !details.metrics) return '';
    
    const metricsHtml = details.metrics.map(m => {
        const barWidth = Math.round(m.normalizedValue * 100);
        const isHigh = m.normalizedValue > 0.6;
        const barClass = isHigh ? 'high' : m.normalizedValue > 0.3 ? 'medium' : 'low';
        
        return `
            <div class="difficulty-metric">
                <div class="metric-header">
                    <span class="metric-name">${m.name}</span>
                    <span class="metric-value">${formatMetricValue(m.name, m.value)}</span>
                </div>
                <div class="metric-bar">
                    <div class="metric-bar-fill ${barClass}" style="width: ${barWidth}%"></div>
                </div>
                <div class="metric-interpretation">${m.interpretation}</div>
            </div>
        `;
    }).join('');
    
    const suggestionsHtml = details.suggestions && details.suggestions.length > 0
        ? `<div class="difficulty-suggestions">
            <strong><i class="fas fa-lightbulb"></i> Рекомендации:</strong>
            <ul>${details.suggestions.map(s => `<li>${s}</li>`).join('')}</ul>
           </div>`
        : '';
    
    return `
        <div class="difficulty-details-content">
            <div class="difficulty-explanation">${details.explanation}</div>
            <div class="difficulty-metrics">${metricsHtml}</div>
            ${suggestionsHtml}
        </div>
    `;
}

/**
 * Рендеринг списка модулей
 */
function renderModulesList(heatmap) {
    if (!heatmap) return;

    const sortedModules = [...heatmap.modules].sort((a, b) => (b.difficultyScore || 0) - (a.difficultyScore || 0));
    document.getElementById('heatmapModules').innerHTML = sortedModules.map((m, index) => {
        const moduleType = m.moduleType || 'unknown';
        const typeIcon = getModuleTypeIcon(moduleType);
        const typeName = getModuleTypeName(moduleType);
        const hasDetails = m.difficultyDetails && m.difficultyDetails.metrics;
        const detailsId = `difficulty-details-${index}`;
        
        const detailsHtml = hasDetails ? renderDifficultyDetails(m.difficultyDetails) : '';
        
        return `
            <div class="module-item ${m.difficultyScore >= 0.6 ? 'hard' : m.difficultyScore >= 0.3 ? 'medium' : 'easy'}" data-module-id="${m.moduleId}">
                <div class="module-main">
                    <div>
                        <strong>${m.moduleName || `Модуль ${m.moduleId}`}</strong>
                        <div class="meta">
                            ${typeIcon} ${typeName} •
                            Отвал: ${(m.dropoutRate * 100).toFixed(0)}% •
                            Просмотр: ${m.watchPercent ? (m.watchPercent * 100).toFixed(0) + '%' : '—'} •
                            ${m.studentCount} студентов
                        </div>
                    </div>
                    <div class="module-actions">
                        <span class="badge badge-${m.difficultyScore >= 0.6 ? 'danger' : m.difficultyScore >= 0.3 ? 'warning' : 'success'}"
                              ${hasDetails ? `onclick="toggleDifficultyDetails('${detailsId}')" style="cursor: pointer;" title="Нажмите для детализации"` : ''}>
                            ${m.difficultyScore.toFixed(2)}
                            ${hasDetails ? '<i class="fas fa-info-circle" style="margin-left: 4px; font-size: 0.8em;"></i>' : ''}
                        </span>
                    </div>
                </div>
                ${hasDetails ? `<div id="${detailsId}" class="difficulty-details" style="display: none;">${detailsHtml}</div>` : ''}
            </div>
        `;
    }).join('');
}

/**
 * Переключение видимости детализации сложности
 */
function toggleDifficultyDetails(detailsId) {
    const details = document.getElementById(detailsId);
    if (details) {
        const isVisible = details.style.display !== 'none';
        details.style.display = isVisible ? 'none' : 'block';
    }
}

/**
 * Рендеринг точек отвала с детальной информацией
 */
function renderDropoffPoints(dropoff) {
    const container = document.getElementById('dropoffPoints');
    
    if (!dropoff || !dropoff.dropoffPoints) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="icon">${icons.chart}</div>
                <p>Данные об отвале не найдены</p>
            </div>
        `;
        return;
    }

    const moduleTypeInfo = {
        'quiz': { icon: 'fa-question-circle', name: 'Тест' },
        'assign': { icon: 'fa-tasks', name: 'Задание' },
        'resource': { icon: 'fa-file', name: 'Файл' },
        'url': { icon: 'fa-link', name: 'Ссылка' },
        'page': { icon: 'fa-file-alt', name: 'Страница' },
        'book': { icon: 'fa-book', name: 'Книга' },
        'label': { icon: 'fa-tag', name: 'Пояснение' },
        'forum': { icon: 'fa-comments', name: 'Форум' },
        'folder': { icon: 'fa-folder', name: 'Папка' },
        'workshop': { icon: 'fa-users-cog', name: 'Семинар' },
        'lesson': { icon: 'fa-graduation-cap', name: 'Лекция' },
        'h5pactivity': { icon: 'fa-puzzle-piece', name: 'H5P' },
        'video': { icon: 'fa-video', name: 'Видео' },
    };

    const getModuleTypeDisplay = (type) => {
        const info = moduleTypeInfo[type?.toLowerCase()] || { icon: 'fa-cube', name: type || 'Модуль' };
        return `<i class="fas ${info.icon}"></i> ${info.name}`;
    };

    let statsHtml = '';
    if (dropoff.totalEnrolled > 0 || dropoff.totalStarted > 0) {
        statsHtml = `
            <div class="dropoff-stats-summary">
                <div class="stats-row">
                    <span class="stats-label"><i class="fas fa-users"></i> Записано на курс:</span>
                    <span class="stats-value">${dropoff.totalEnrolled || '—'}</span>
                </div>
                <div class="stats-row">
                    <span class="stats-label"><i class="fas fa-play-circle"></i> Начали курс:</span>
                    <span class="stats-value">${dropoff.totalStarted || '—'}</span>
                </div>
            </div>
        `;
    }

    const methodologyHtml = `
        <div class="dropoff-methodology">
            <i class="fas fa-info-circle"></i>
            <span>${dropoff.methodologyExplanation || 'Процент отвала показывает долю студентов, которые открыли модуль, но не перешли к следующим модулям курса.'}</span>
        </div>
    `;

    const pointsHtml = dropoff.dropoffPoints.map(p => {
        const dropoutPercent = (p.dropoutRate * 100).toFixed(0);
        const continuedPercent = (100 - dropoutPercent).toFixed(0);
        const avgTime = p.avgTimeBeforeDropout ? formatDuration(p.avgTimeBeforeDropout) : '—';
        const moduleTypeDisplay = getModuleTypeDisplay(p.moduleType);
        
        const badgeClass = dropoutPercent >= 50 ? 'badge-danger' : 'badge-warning';
        
        return `
            <div class="dropoff-item">
                <div class="dropoff-header">
                    <div class="dropoff-title">
                        <strong>${p.moduleName || `Модуль ${p.moduleId}`}</strong>
                        <span class="badge ${badgeClass}" title="Процент студентов, не перешедших к следующим модулям">${dropoutPercent}% отвал</span>
                    </div>
                    <div class="dropoff-meta">
                        ${moduleTypeDisplay} • Шаг ${p.step}
                    </div>
                </div>
                <div class="dropoff-details">
                    <div class="dropoff-stat">
                        <span class="stat-icon"><i class="fas fa-sign-in-alt"></i></span>
                        <span class="stat-label">Открыли модуль:</span>
                        <span class="stat-value">${p.studentsEntered}</span>
                    </div>
                    <div class="dropoff-stat">
                        <span class="stat-icon"><i class="fas fa-arrow-right"></i></span>
                        <span class="stat-label">Продолжили дальше:</span>
                        <span class="stat-value success">${p.studentsContinued || (p.studentsEntered - p.studentsDropped)} (${continuedPercent}%)</span>
                    </div>
                    <div class="dropoff-stat">
                        <span class="stat-icon"><i class="fas fa-times-circle"></i></span>
                        <span class="stat-label">Не перешли дальше:</span>
                        <span class="stat-value danger">${p.studentsDropped} (${dropoutPercent}%)</span>
                    </div>
                    <div class="dropoff-stat">
                        <span class="stat-icon"><i class="fas fa-clock"></i></span>
                        <span class="stat-label">Среднее время в модуле:</span>
                        <span class="stat-value">${avgTime}</span>
                    </div>
                </div>
            </div>
        `;
    }).join('');

    container.innerHTML = statsHtml + methodologyHtml + pointsHtml;
}

/**
 * Форматирование длительности в читаемый вид
 */
function formatDuration(ms) {
    if (ms == null || ms < 0) return '—';

    const seconds = Math.floor(ms / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);
    
    if (hours > 0) {
        return `${hours} ч ${minutes % 60} мин`;
    } else if (minutes > 0) {
        return `${minutes} мин ${seconds % 60} сек`;
    } else {
        return `${seconds} сек`;
    }
}

/**
 * Рендеринг вкладки "Медиа и рекомендации"
 */
function renderMedia(video, recommendations) {
    renderVideo(video);
    renderRecommendations(recommendations);
}

/**
 * Рендеринг видео аналитики с группировкой по модулям
 */
function renderVideo(video) {
    if (!video || !video.videos || video.videos.length === 0) {
        document.getElementById('videoAnalytics').innerHTML = `
            <div class="empty-state">
                <div class="icon">${icons.video}</div>
                <p>Данные по видео не найдены</p>
            </div>
        `;
        return;
    }

    const groupedByModule = {};
    video.videos.forEach(v => {
        const moduleName = v.moduleName || `Модуль ${v.moduleId}`;
        if (!groupedByModule[moduleName]) {
            groupedByModule[moduleName] = [];
        }
        groupedByModule[moduleName].push(v);
    });

    let html = '';
    for (const [moduleName, videos] of Object.entries(groupedByModule)) {
        html += `
            <div class="video-module-group">
                <h3 class="module-group-title">
                    <i class="fas fa-folder-open"></i> ${moduleName}
                </h3>
                ${videos.map(v => renderVideoItem(v)).join('')}
            </div>
        `;
    }
    
    document.getElementById('videoAnalytics').innerHTML = html;
}

/**
 * Рендеринг одного видео элемента
 */
function renderVideoItem(v) {
    const fileName = v.mediaId ? v.mediaId.split('/').pop() : 'Видео';
    
    return `
        <div class="video-item">
            <div class="video-header">
                <h4><i class="fas fa-film"></i> ${fileName}</h4>
                <span class="video-type-badge">${v.mediaType}</span>
            </div>
            <div class="video-meta">
                ${v.videoDurationMs ? `<span><i class="fas fa-clock"></i> Длительность: ${formatDuration(v.videoDurationMs)}</span>` : ''}
                ${v.avgTotalWatchTime ? `<span><i class="fas fa-eye"></i> Среднее время просмотра: ${formatDuration(v.avgTotalWatchTime)}</span>` : ''}
            </div>
            <div class="video-stats">
                <div class="video-stat"><strong>${v.uniqueUsers}</strong> студентов</div>
                <div class="video-stat"><strong>${v.avgWatchPercent ? v.avgWatchPercent.toFixed(0) + '%' : '—'}</strong> просмотр</div>
                <div class="video-stat"><strong>${v.pauseCount}</strong> пауз</div>
                <div class="video-stat"><strong>${v.seekCount}</strong> перемоток</div>
            </div>
            <h5 class="segments-title"><i class="fas fa-film"></i> Просмотр по отрезкам видео</h5>
            <div class="segments">
                ${v.segments.map(s => renderSegment(s, v)).join('')}
            </div>
            ${renderPauseHotspots(v.pauseHotspots)}
            ${renderSeekPatterns(v.seekPatterns)}
        </div>
    `;
}

/**
 * Рендеринг сегмента видео с цветовой индикацией
 */
function renderSegment(s, video) {
    let segmentClass = '';
    if (s.isWellWatched) {
        segmentClass = 'well-watched';
    } else if (s.isLeastWatched) {
        segmentClass = 'least-watched';
    }
    
    let timeDisplay;
    if (s.segmentDuration && s.segmentDuration > 0) {
        timeDisplay = `${formatDuration(s.avgWatchTime)} / ${formatDuration(s.segmentDuration)}`;
    } else {
        timeDisplay = formatDuration(s.avgWatchTime);
    }
    
    let percentDisplay;
    if (s.watchPercent !== null && s.watchPercent !== undefined) {
        percentDisplay = `${s.watchPercent.toFixed(0)}%`;
    } else {
        percentDisplay = `${(s.watchShare * 100).toFixed(0)}%`;
    }


    return `
        <div class="segment ${segmentClass}">
            <div class="segment-label"></i> ${s.segment}%</div>
            <div class="time">${timeDisplay}</div>
            <div class="share">${percentDisplay} просмотрено</div>
            ${s.pauseCount > 0 ? `<div class="pause-indicator"><i class="fas fa-pause"></i> ${s.pauseCount}</div>` : ''}
        </div>
    `;
}

/**
 * Рендеринг точек частых пауз
 */
function renderPauseHotspots(hotspots) {
    if (!hotspots || hotspots.length === 0) return '';
    
    return `
        <div class="pause-hotspots">
            <h5><i class="fas fa-pause-circle"></i> Паузы по отрезкам</h5>
            <div class="hotspots-list">
                ${hotspots.map(h => `
                    <span class="hotspot-badge">
                        ${h.segment}%: ${h.pauseCount} пауз
                        ${h.avgPauseTime ? `(~${formatDuration(h.avgPauseTime)})` : ''}
                    </span>
                `).join('')}
            </div>
        </div>
    `;
}

/**
 * Рендеринг паттернов перемоток
 */

function renderSeekPatterns(patterns) {
    if (!patterns || patterns.length === 0) return '';
    const sorted = [...patterns].sort((a, b) => b.count - a.count).slice(0, 5);

    return `
        <div class="seek-patterns">
            <h5><i class="fas fa-forward"></i> Перемотки</h5>
            <div class="patterns-list">
                ${sorted.map(p => {
                    const from = formatDuration(p.avgFromTimeMs || 0);
                    const to = formatDuration(p.avgToTimeMs || 0);
                    const arrow = p.isBackward ? '←' : '→';
                    return `
                    <span class="pattern-badge ${p.isBackward ? 'backward' : 'forward'}">
                        ${from} ${arrow} ${to}: ${p.count}x
                    </span>`;
                }).join('')}
            </div>
        </div>
    `;
}

/**
 * Рендеринг рекомендаций
 */
function renderRecommendations(recs) {
    if (!recs || !recs.recommendations || recs.recommendations.length === 0) {
        document.getElementById('recommendationsList').innerHTML = `
            <div class="empty-state">
                <div class="icon">${icons.lightbulb}</div>
                <p>Рекомендации не найдены</p>
            </div>
        `;
        return;
    }

    document.getElementById('recommendationsList').innerHTML = recs.recommendations.map(r => `
        <div class="recommendation-item">
            <div style="display: flex; justify-content: space-between; align-items: start;">
                <strong>${r.moduleName || `Модуль ${r.moduleId}`}</strong>
                <span class="badge badge-${r.priority === 'high' ? 'danger' : r.priority === 'medium' ? 'warning' : 'success'}">${r.priority}</span>
            </div>
            <div class="issue"><i class="fas fa-exclamation-triangle"></i> ${r.issue}</div>
            <div class="suggestion"><i class="fas fa-lightbulb"></i> ${r.recommendation}</div>
        </div>
    `).join('');
}
