

// pdf-lib must be imported via importScripts inside a worker
importScripts('https://unpkg.com/pdf-lib@1.17.1/dist/pdf-lib.min.js');

/* ================================================================
   CONFIG — tweak these if layout or performance needs adjusting
================================================================ */
const BATCH_SIZE = 10;         // students fetched concurrently per batch
const BATCH_DELAY_MS = 100;    // ms pause between batches (server breathing room)
const FETCH_TIMEOUT_MS = 15000; // per-student fetch timeout in ms

/* ================================================================
   ENTRY POINT — receives message from main thread
   Expected payload: { students, apiBase, csrfToken }
================================================================ */
self.onmessage = async (e) => {
    const { students, apiBase, csrfToken } = e.data;

    if (!students || !students.length) {
        self.postMessage({ type: 'error', message: 'No students to generate report for.' });
        return;
    }

    try {
        self.postMessage({ type: 'status', message: 'Initialising PDF...', progress: 0, total: students.length });

        // ---- PHASE 1: Fetch all student audit data in batches ----
        const studentDataList = [];
        let fetched = 0;

        for (let i = 0; i < students.length; i += BATCH_SIZE) {
            const batch = students.slice(i, i + BATCH_SIZE);

            // Fetch all students in this batch concurrently
            const results = await Promise.allSettled(
                batch.map(s => fetchStudentData(apiBase, s.student_number, csrfToken))
            );

            // Collect results — failed fetches get a placeholder so the PDF still builds
            results.forEach((result, idx) => {
                if (result.status === 'fulfilled') {
                    studentDataList.push(result.value);
                } else {
                    studentDataList.push({
                        student_number: batch[idx].student_number,
                        name: batch[idx].name,
                        programme: batch[idx].programme || '',
                        major: batch[idx].major || '',
                        overall_gpa: batch[idx].overall_gpa || null,
                        has_audit: false,
                        fetch_error: true,
                        can_graduate: false,
                        bucket_results: [],
                        unmet_requirements: [],
                        next_steps: [],
                    });
                }
            });

            fetched += batch.length;
            self.postMessage({
                type: 'progress',
                phase: 'fetching',
                message: `Fetching student data... ${fetched} / ${students.length}`,
                progress: fetched,
                total: students.length,
            });

            // Brief pause between batches to avoid hammering the server
            if (i + BATCH_SIZE < students.length) {
                await sleep(BATCH_DELAY_MS);
            }
        }

        // ---- PHASE 2: Build the PDF from fetched data ----
        self.postMessage({ type: 'status', message: 'Building PDF...', progress: 0, total: studentDataList.length });

        const pdfBytes = await buildPdf(studentDataList, (built, total) => {
            self.postMessage({
                type: 'progress',
                phase: 'building',
                message: `Building PDF... ${built} / ${total}`,
                progress: built,
                total: total,
            });
        });

        // ---- DONE — send bytes back to main thread ----
        self.postMessage({ type: 'done', pdfBytes });

    } catch (err) {
        self.postMessage({ type: 'error', message: err.message || 'Unknown error during PDF generation.' });
    }
};

/* ================================================================
   FETCH STUDENT DATA
   Hits the API for a single student's full audit record.
   Aborts after FETCH_TIMEOUT_MS to prevent hanging.
================================================================ */
async function fetchStudentData(apiBase, studentNumber, csrfToken) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);

    try {
        const res = await fetch(`${apiBase}${studentNumber}/`, {
            headers: {
                'X-CSRFToken': csrfToken,
                'Accept': 'application/json',
            },
            signal: controller.signal,
        });

        if (!res.ok) throw new Error(`HTTP ${res.status} for student ${studentNumber}`);
        return await res.json();

    } finally {
        clearTimeout(timeout);
    }
}

/* ================================================================
   TRUNCATE TEXT
   Trims a string until it fits within maxWidth at the given font/size.
   Prevents text from overflowing card boundaries in the PDF.
   
   @param {string} text      - The text to truncate
   @param {PDFFont} font     - pdf-lib font object (has widthOfTextAtSize)
   @param {number} size      - Font size in points
   @param {number} maxWidth  - Maximum allowed width in points
   @returns {string}         - Truncated string that fits within maxWidth
================================================================ */
function truncateText(text, font, size, maxWidth) {
    if (!text) return '';
    let str = String(text);
    while (str.length > 0 && font.widthOfTextAtSize(str, size) > maxWidth) {
        str = str.slice(0, -1);
    }
    return str;
}

/* ================================================================
   BUILD PDF
   Creates the full pdf-lib document, adds one page per student,
   then prepends a cover page summarising the batch.
================================================================ */
async function buildPdf(studentDataList, onProgress) {
    const { PDFDocument, rgb, StandardFonts, PageSizes } = PDFLib;

    const pdfDoc = await PDFDocument.create();
    const fontBold = await pdfDoc.embedFont(StandardFonts.HelveticaBold);
    const fontRegular = await pdfDoc.embedFont(StandardFonts.Helvetica);

    // ---- COLOUR PALETTE ----
    const CLR_PRIMARY = rgb(0.106, 0.639, 0.518);  // #2ba384 — brand green
    const CLR_DANGER = rgb(1, 0.302, 0.302);       // #ff4d4d — red for not eligible
    const CLR_TEXT = rgb(0.067, 0.094, 0.153);   // #111827 — near black body text
    const CLR_MUTED = rgb(0.443, 0.502, 0.588);   // #718096 — grey labels
    const CLR_BORDER = rgb(0.886, 0.910, 0.941);   // #e2e8f0 — light card border
    const CLR_ELIGIBLE_BG = rgb(0.894, 0.961, 0.933);   // light green badge background
    const CLR_DANGER_BG = rgb(1, 0.922, 0.922);        // light red badge background
    const CLR_WHITE = rgb(1, 1, 1);
    const CLR_LIGHT_BG = rgb(0.980, 0.980, 0.980);   // off-white card background

    // ---- PAGE DIMENSIONS (A4) ----
    const PAGE_W = PageSizes.A4[0];
    const PAGE_H = PageSizes.A4[1];
    const MARGIN = 50;
    const COL_W = PAGE_W - MARGIN * 2;

    // Bundle shared drawing context to avoid passing dozens of params
    const ctx = {
        fontBold, fontRegular,
        CLR_PRIMARY, CLR_DANGER, CLR_TEXT, CLR_MUTED, CLR_BORDER,
        CLR_ELIGIBLE_BG, CLR_DANGER_BG, CLR_WHITE, CLR_LIGHT_BG,
        PAGE_W, PAGE_H, MARGIN, COL_W,
        pdfDoc,
        addPage: () => pdfDoc.addPage(PageSizes.A4),
    };

    // One page per student
    for (let i = 0; i < studentDataList.length; i++) {
        const student = studentDataList[i];
        const page = pdfDoc.addPage(PageSizes.A4);
        drawStudentPage(page, student, ctx);
        onProgress(i + 1, studentDataList.length);
    }

    // Cover page is inserted at position 0 after all student pages are built
    const coverPage = pdfDoc.insertPage(0, PageSizes.A4);
    drawCoverPage(coverPage, studentDataList, ctx);

    return await pdfDoc.save();
}

/* ================================================================
   DRAW COVER PAGE
   Summary page prepended to the report showing totals and
   a full index of all students with their pass/fail status.
================================================================ */
function drawCoverPage(page, students, ctx) {
    const {
        fontBold, fontRegular,
        CLR_PRIMARY, CLR_TEXT, CLR_MUTED, CLR_WHITE, CLR_BORDER,
        PAGE_W, PAGE_H, MARGIN,
    } = ctx;

    // ---- HEADER BAND ----
    page.drawRectangle({ x: 0, y: PAGE_H - 120, width: PAGE_W, height: 120, color: CLR_PRIMARY });

    page.drawText('Student Grids', {
        x: MARGIN, y: PAGE_H - 55,
        font: fontBold, size: 28, color: CLR_WHITE,
    });
    page.drawText('Graduation Eligibility Report', {
        x: MARGIN, y: PAGE_H - 85,
        font: fontRegular, size: 14, color: CLR_WHITE, opacity: 0.85,
    });

    const now = new Date();
    page.drawText(
        `Generated: ${now.toLocaleDateString('en-GB', { day: '2-digit', month: 'long', year: 'numeric' })}`,
        { x: MARGIN, y: PAGE_H - 105, font: fontRegular, size: 9, color: CLR_WHITE, opacity: 0.7 }
    );

    // ---- SUMMARY STAT CARDS ----
    const total = students.length;
    const eligible = students.filter(s => s.can_graduate).length;
    const notEligible = total - eligible;

    const stats = [
        { label: 'Total Students', value: total },
        { label: 'Eligible', value: eligible },
        { label: 'Not Eligible', value: notEligible },
    ];

    let sx = MARGIN;
    const statW = (PAGE_W - MARGIN * 2) / 3 - 10;

    stats.forEach(stat => {
        page.drawRectangle({
            x: sx, y: PAGE_H - 220, width: statW, height: 70,
            color: CLR_WHITE, borderColor: CLR_BORDER, borderWidth: 1,
        });
        page.drawText(String(stat.value), {
            x: sx + 12, y: PAGE_H - 175,
            font: fontBold, size: 22, color: CLR_TEXT,
        });
        page.drawText(stat.label, {
            x: sx + 12, y: PAGE_H - 195,
            font: fontRegular, size: 9, color: CLR_MUTED,
        });
        sx += statW + 15;
    });

    // ---- STUDENT INDEX LIST ----
    page.drawText('Students in this report:', {
        x: MARGIN, y: PAGE_H - 255,
        font: fontBold, size: 11, color: CLR_TEXT,
    });

    let ly = PAGE_H - 275;
    students.forEach((s, idx) => {
        if (ly < MARGIN + 20) return; // Stop if we've run out of page space
        // WinAnsi-safe status markers instead of Unicode checkmarks
        const statusMarker = s.can_graduate ? '[PASS]' : '[FAIL]';
        page.drawText(`${statusMarker}  ${idx + 1}.  ${s.name}  --  ${s.student_number}`, {
            x: MARGIN, y: ly,
            font: fontRegular, size: 9, color: CLR_TEXT,
        });
        ly -= 16;
    });
}

/* ================================================================
   DRAW STUDENT PAGE
   Full audit detail page for one student.
   Automatically adds new pages if content overflows.
================================================================ */
function drawStudentPage(firstPage, student, ctx) {
    const {
        fontBold, fontRegular,
        CLR_PRIMARY, CLR_DANGER, CLR_TEXT, CLR_MUTED, CLR_BORDER,
        CLR_ELIGIBLE_BG, CLR_DANGER_BG, CLR_WHITE, CLR_LIGHT_BG,
        PAGE_W, PAGE_H, MARGIN, COL_W,
        addPage,
    } = ctx;

    let page = firstPage;
    let y = PAGE_H - MARGIN;

    // Adds a fresh page if the next block won't fit
    function ensureSpace(needed) {
        if (y - needed < MARGIN + 30) {
            page = addPage();
            y = PAGE_H - MARGIN;
        }
    }

    // Draws a horizontal rule using the border colour
    function drawLine(x1, y1, x2, thickness = 0.5) {
        page.drawLine({
            start: { x: x1, y: y1 },
            end: { x: x2, y: y1 },
            thickness,
            color: CLR_BORDER,
        });
    }

    // ---- HEADER BAND ----
    page.drawRectangle({ x: 0, y: PAGE_H - 90, width: PAGE_W, height: 90, color: CLR_PRIMARY });

    // Student name — truncated to prevent overflow into the badge area
    const nameMaxWidth = PAGE_W - MARGIN * 2 - 100;
    page.drawText(truncateText(student.name || 'Unknown Student', fontBold, 20, nameMaxWidth), {
        x: MARGIN, y: PAGE_H - 38,
        font: fontBold, size: 20, color: CLR_WHITE,
    });

    page.drawText(String(student.student_number || ''), {
        x: MARGIN, y: PAGE_H - 58,
        font: fontRegular, size: 10, color: CLR_WHITE, opacity: 0.85,
    });

    // Eligibility badge (top right of header)
    const eligible = student.can_graduate;
    const badgeText = eligible ? 'ELIGIBLE' : 'NOT ELIGIBLE';
    const badgeClr = eligible ? CLR_ELIGIBLE_BG : CLR_DANGER_BG;
    const badgeTxt = eligible ? CLR_PRIMARY : CLR_DANGER;
    const badgeW = eligible ? 62 : 82;

    page.drawRectangle({
        x: PAGE_W - MARGIN - badgeW, y: PAGE_H - 52,
        width: badgeW, height: 20,
        color: badgeClr, borderRadius: 4,
    });
    page.drawText(badgeText, {
        x: PAGE_W - MARGIN - badgeW + 8, y: PAGE_H - 44,
        font: fontBold, size: 8, color: badgeTxt,
    });

    if (student.audit_date) {
        page.drawText(`Audit: ${student.audit_date}`, {
            x: MARGIN, y: PAGE_H - 76,
            font: fontRegular, size: 8, color: CLR_WHITE, opacity: 0.7,
        });
    }

    y = PAGE_H - 110;

    // ---- FETCH ERROR STATE ----
    // Shown when API fetch failed for this student — still produces a page
    if (student.fetch_error) {
        ensureSpace(40);
        page.drawText('! Error: Could not load data for this student.', {
            x: MARGIN, y,
            font: fontRegular, size: 10, color: CLR_DANGER,
        });
        y -= 30;
        return;
    }

    // ---- OVERVIEW CARDS ----
    // Four info cards: Programme, Major, GPA, Credits Earned
    const overviewItems = [
        { label: 'Programme', value: student.evaluated_programme || student.programme || '-' },
        { label: 'Major', value: student.evaluated_major || student.major || '-' },
        { label: 'GPA', value: student.overall_gpa != null ? Number(student.overall_gpa).toFixed(2) : '-' },
        { label: 'Credits Earned', value: `${Number(student.total_credits_earned || 0).toFixed(0)} / ${Number(student.total_credits_required || 0).toFixed(0)}` },
    ];

    ensureSpace(130);
    const fullW = COL_W;
    const halfW = (COL_W - 6) / 2;
    const CARD_H = 40;
    const GAP = 6;

    // Row 1 — Programme (full width)
    page.drawRectangle({
        x: MARGIN, y: y - 36, width: fullW, height: CARD_H,
        color: CLR_LIGHT_BG, borderColor: CLR_BORDER, borderWidth: 0.5
    });
    page.drawText('Programme', {
        x: MARGIN + 8, y: y - 15,
        font: fontRegular, size: 7.5, color: CLR_MUTED
    });
    page.drawText(truncateText(String(overviewItems[0].value), fontBold, 9.5, fullW - 16), {
        x: MARGIN + 8, y: y - 28, font: fontBold, size: 9.5, color: CLR_TEXT
    });
    y -= CARD_H + GAP;

    // Row 2 — Major (full width)
    page.drawRectangle({
        x: MARGIN, y: y - 36, width: fullW, height: CARD_H,
        color: CLR_LIGHT_BG, borderColor: CLR_BORDER, borderWidth: 0.5
    });
    page.drawText('Major', {
        x: MARGIN + 8, y: y - 15,
        font: fontRegular, size: 7.5, color: CLR_MUTED
    });
    page.drawText(truncateText(String(overviewItems[1].value), fontBold, 9.5, fullW - 16), {
        x: MARGIN + 8, y: y - 28, font: fontBold, size: 9.5, color: CLR_TEXT
    });
    y -= CARD_H + GAP;

    // Row 3 — GPA (left half) + Credits Earned (right half)
    [overviewItems[2], overviewItems[3]].forEach((item, idx) => {
        const cx = MARGIN + idx * (halfW + GAP);
        page.drawRectangle({
            x: cx, y: y - 36, width: halfW, height: CARD_H,
            color: CLR_LIGHT_BG, borderColor: CLR_BORDER, borderWidth: 0.5
        });
        page.drawText(item.label, {
            x: cx + 8, y: y - 15,
            font: fontRegular, size: 7.5, color: CLR_MUTED
        });
        page.drawText(truncateText(String(item.value), fontBold, 9.5, halfW - 16), {
            x: cx + 8, y: y - 28, font: fontBold, size: 9.5, color: CLR_TEXT
        });
    });
    y -= CARD_H + GAP;

    // ---- NO AUDIT STATE ----
    if (!student.has_audit) {
        ensureSpace(30);
        page.drawText('No audit record found.', {
            x: MARGIN, y,
            font: fontRegular, size: 10, color: CLR_MUTED,
        });
        return;
    }

    // ---- BUCKET RESULTS ----
    // Group buckets by component_name (e.g. "Computer Science", "General Requirements")
    const components = {};
    (student.bucket_results || []).forEach(b => {
        if (!components[b.component_name]) components[b.component_name] = [];
        components[b.component_name].push(b);
    });

    for (const [compName, buckets] of Object.entries(components)) {

        // Component heading band
        ensureSpace(30);
        page.drawRectangle({
            x: MARGIN, y: y - 18, width: COL_W, height: 22,
            color: CLR_PRIMARY, borderRadius: 2,
        });
        page.drawText(truncateText(compName, fontBold, 10, COL_W - 16), {
            x: MARGIN + 8, y: y - 10,
            font: fontBold, size: 10, color: CLR_WHITE,
        });
        y -= 28;

        for (const bucket of buckets) {
            ensureSpace(50);

            // WinAnsi-safe status marker instead of Unicode tick/cross
            const bucketMet = bucket.is_met;
            const statusText = bucketMet ? '[MET]' : '[NOT MET]';
            const statusClr = bucketMet ? CLR_PRIMARY : CLR_DANGER;

            page.drawText(statusText, {
                x: MARGIN, y,
                font: fontBold, size: 8, color: statusClr,
            });

            // Bucket name — truncated to prevent overlap with credit count on right
            const bucketNameMaxW = COL_W - 120;
            page.drawText(truncateText(bucket.bucket_name || '', fontBold, 9.5, bucketNameMaxW), {
                x: MARGIN + 45, y,
                font: fontBold, size: 9.5, color: CLR_TEXT,
            });

            // Credit count (right-aligned)
            page.drawText(
                `${Number(bucket.credits_earned || 0).toFixed(0)} / ${Number(bucket.credits_required || 0).toFixed(0)} cr`,
                { x: PAGE_W - MARGIN - 60, y, font: fontRegular, size: 8.5, color: CLR_MUTED }
            );

            drawLine(MARGIN, y - 4, PAGE_W - MARGIN);
            y -= 14;

            // Completed courses for this bucket
            const completed = bucket.courses_completed || [];
            if (completed.length) {
                ensureSpace(16);
                page.drawText('Completed:', {
                    x: MARGIN + 10, y,
                    font: fontBold, size: 8, color: CLR_PRIMARY,
                });
                y -= 12;
                completed.forEach(course => {
                    ensureSpace(12);
                    page.drawText(`- ${course.code || '-'}`, {
                        x: MARGIN + 14, y,
                        font: fontRegular, size: 8, color: CLR_TEXT,
                    });
                    y -= 11;
                });
            }

            // Courses still needed for this bucket
            const needed = bucket.courses_needed || [];
            if (needed.length) {
                ensureSpace(16);
                page.drawText('Needed:', {
                    x: MARGIN + 10, y,
                    font: fontBold, size: 8, color: CLR_DANGER,
                });
                y -= 12;
                needed.forEach(course => {
                    ensureSpace(12);
                    // courses_needed can be either a string code or an object with a code key
                    const label = typeof course === 'string' ? course : (course.code || '-');
                    page.drawText(`- ${label}`, {
                        x: MARGIN + 14, y,
                        font: fontRegular, size: 8, color: CLR_TEXT,
                    });
                    y -= 11;
                });
            }

            y -= 8; // Gap between buckets
        }
    }

    // ---- UNMET REQUIREMENTS SECTION ----
    const unmet = student.unmet_requirements || [];
    if (unmet.length) {
        ensureSpace(40);
        page.drawRectangle({
            x: MARGIN, y: y - 18, width: COL_W, height: 22,
            color: CLR_DANGER, borderRadius: 2,
        });
        page.drawText('Unmet Requirements', {
            x: MARGIN + 8, y: y - 10,
            font: fontBold, size: 10, color: CLR_WHITE,
        });
        y -= 28;

        unmet.forEach(req => {
            ensureSpace(14);
            page.drawText(`- ${String(req)}`, {
                x: MARGIN + 8, y,
                font: fontRegular, size: 8.5, color: CLR_TEXT,
            });
            y -= 13;
        });
    }

    // ---- PAGE FOOTER ----
    page.drawText(`Student Grids  --  Confidential  --  ${new Date().getFullYear()}`, {
        x: MARGIN, y: MARGIN - 15,
        font: fontRegular, size: 7.5, color: CLR_MUTED,
    });
}

/* ================================================================
   UTILITY
================================================================ */
function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}