import { storage } from '../../scripts/storage.js';

export const initManualScan = (navigate) => {
  const form = document.getElementById('manual-scan-form');
  const resultsScreen = document.getElementById('results-screen');
  const analyzeBtn = document.getElementById('analyze-btn');
  const backBtn = document.getElementById('back-to-form-btn');
  const draftBtn = document.getElementById('draft-btn');
  const reportBtn = document.getElementById('report-job-btn');
  
  // Results Elements
  const scoreDisplay = document.getElementById('result-score');
  const statusBadge = document.getElementById('result-status-badge');
  const recommendation = document.getElementById('result-recommendation');
  const riskList = document.getElementById('risk-factors-list');
  const riskContainer = document.getElementById('risk-factors-container');
  const positiveList = document.getElementById('positive-signals-list');
  const positiveContainer = document.getElementById('positive-signals-container');
  const glow = document.getElementById('score-bg-glow');

  // Specific Frontend Analysis Checks
  const manualChecks = [
    {
      name: "Personal Email Detection",
      risk: "medium",
      keywords: ["@gmail.com", "@yahoo.com", "@hotmail.com", "@outlook.com"],
      check: (data) => data.recruiterEmail && data.recruiterEmail.match(/@(gmail|yahoo|hotmail|outlook)\.com/i),
      message: "Recruiter uses a personal email address rather than a corporate domain.",
      weight: 20
    },
    {
      name: "Fee Request Detection",
      risk: "high",
      keywords: ["registration fee", "application fee", "processing fee", "training fee", "payment required", "mpesa payment"],
      check: (data) => {
        if (data.applicationFee === "Yes") return true;
        const text = `${data.requirements} ${data.description}`.toLowerCase();
        return ["registration fee", "application fee", "processing fee", "training fee", "payment required", "mpesa"].some(kw => text.includes(kw));
      },
      message: "Job mentions application or registration fees, which is a common scam indicator.",
      weight: 40
    },
    {
      name: "Urgency Manipulation Detection",
      risk: "medium",
      keywords: ["urgent hiring", "limited slots", "apply immediately", "guaranteed job"],
      check: (data) => {
        const text = `${data.requirements} ${data.description} ${data.jobTitle}`.toLowerCase();
        return ["urgent", "limited slots", "apply immediately", "guaranteed"].some(kw => text.includes(kw));
      },
      message: "Listing uses high-pressure or urgency language ('urgent', 'guaranteed').",
      weight: 15
    },
    {
      name: "Missing Website Check",
      risk: "medium",
      check: (data) => !data.companyWebsite,
      message: "No corporate website provided, making verification harder.",
      weight: 10
    },
    {
      name: "Telegram/WhatsApp Interview",
      risk: "high",
      check: (data) => ["Telegram", "WhatsApp"].includes(data.interviewMethod),
      message: "Interviews conducted via messaging apps are common in recruitment fraud.",
      weight: 30
    }
  ];

  const positiveChecks = [
    {
      name: "Corporate Email",
      check: (data) => data.recruiterEmail && !data.recruiterEmail.match(/@(gmail|yahoo|hotmail|outlook)\.com/i),
      message: "Uses a custom corporate email domain."
    },
    {
      name: "Has Website",
      check: (data) => !!data.companyWebsite,
      message: "Company website provided for verification."
    }
  ];

  const performAnalysis = (data) => {
    let score = 100;
    const risks = [];
    const positives = [];

    // Run risk checks
    manualChecks.forEach(check => {
      if (check.check(data)) {
        score -= check.weight;
        risks.push({
          message: check.message,
          level: check.risk
        });
      }
    });

    // Run positive checks
    positiveChecks.forEach(check => {
      if (check.check(data)) {
        positives.push(check.message);
      }
    });

    // Enforce bounds
    score = Math.max(0, score);

    let status = "safe";
    if (score < 40) status = "danger";
    else if (score < 70) status = "warning";

    return { score, risks, positives, status };
  };

  const displayResults = (analysis) => {
    form.classList.add('hidden');
    resultsScreen.classList.remove('hidden');

    scoreDisplay.textContent = analysis.score;
    
    // Clear lists
    riskList.innerHTML = '';
    positiveList.innerHTML = '';
    
    statusBadge.className = 'px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider mb-3';
    
    if (analysis.status === 'safe') {
      statusBadge.classList.add('bg-green-100', 'text-green-800', 'dark:bg-green-900/30', 'dark:text-green-400');
      statusBadge.textContent = 'Safe';
      scoreDisplay.className = 'text-5xl font-black text-success';
      glow.className = 'absolute inset-0 opacity-20 blur-xl bg-success';
      recommendation.textContent = 'This opportunity shows strong signs of legitimacy. Continue with standard precautions.';
    } else if (analysis.status === 'warning') {
      statusBadge.classList.add('bg-yellow-100', 'text-yellow-800', 'dark:bg-yellow-900/30', 'dark:text-yellow-400');
      statusBadge.textContent = 'Caution';
      scoreDisplay.className = 'text-5xl font-black text-warning';
      glow.className = 'absolute inset-0 opacity-20 blur-xl bg-warning';
      recommendation.textContent = 'Proceed with caution. Several suspicious indicators were found. Verify the company independently.';
    } else {
      statusBadge.classList.add('bg-red-100', 'text-red-800', 'dark:bg-red-900/30', 'dark:text-red-400');
      statusBadge.textContent = 'High Risk';
      scoreDisplay.className = 'text-5xl font-black text-danger';
      glow.className = 'absolute inset-0 opacity-20 blur-xl bg-danger';
      recommendation.textContent = 'High probability of a scam. We strongly advise against sharing personal information, documents, or paying any fees.';
    }

    if (analysis.risks.length > 0) {
      riskContainer.classList.remove('hidden');
      analysis.risks.forEach(risk => {
        const li = document.createElement('li');
        li.className = `text-xs p-2 rounded border-l-2 ${risk.level === 'high' ? 'bg-red-50 border-red-500 text-red-700 dark:bg-red-900/10 dark:text-red-400' : 'bg-yellow-50 border-yellow-500 text-yellow-700 dark:bg-yellow-900/10 dark:text-yellow-400'}`;
        li.textContent = risk.message;
        riskList.appendChild(li);
      });
    } else {
      riskContainer.classList.add('hidden');
    }

    if (analysis.positives.length > 0) {
      positiveContainer.classList.remove('hidden');
      analysis.positives.forEach(pos => {
        const li = document.createElement('li');
        li.className = 'text-xs p-2 rounded bg-green-50 border-l-2 border-green-500 text-green-700 dark:bg-green-900/10 dark:text-green-400';
        li.textContent = pos;
        positiveList.appendChild(li);
      });
    } else {
      positiveContainer.classList.add('hidden');
    }
  };

  form.addEventListener('submit', (e) => {
    e.preventDefault();
    
    // Animate button
    const originalContent = analyzeBtn.innerHTML;
    analyzeBtn.innerHTML = '<svg class="animate-spin h-5 w-5 mr-2 inline" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg> Analyzing...';
    analyzeBtn.disabled = true;

    const formData = new FormData(form);
    const data = Object.fromEntries(formData.entries());

    setTimeout(() => {
      const analysis = performAnalysis(data);
      displayResults(analysis);
      analyzeBtn.innerHTML = originalContent;
      analyzeBtn.disabled = false;
    }, 600); // Simulate processing time
  });

  backBtn.addEventListener('click', () => {
    resultsScreen.classList.add('hidden');
    form.classList.remove('hidden');
  });

  // Load draft if exists
  storage.get(['manualScanDraft']).then(res => {
    if (res.manualScanDraft) {
      Object.entries(res.manualScanDraft).forEach(([key, value]) => {
        const field = form.elements[key];
        if (field) {
          if (field.type === 'radio') {
            const radio = Array.from(form.elements[key]).find(r => r.value === value);
            if (radio) radio.checked = true;
          } else {
            field.value = value;
          }
        }
      });
    }
  });

  draftBtn.addEventListener('click', () => {
    const formData = new FormData(form);
    const data = Object.fromEntries(formData.entries());
    storage.set({ manualScanDraft: data }).then(() => {
      const origText = draftBtn.textContent;
      draftBtn.textContent = 'Saved!';
      setTimeout(() => draftBtn.textContent = origText, 2000);
    });
  });

  reportBtn.addEventListener('click', () => {
    // Navigate to report tab and ideally prefill, but standard navigation for now
    navigate('report');
  });
};
