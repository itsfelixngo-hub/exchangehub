(function(){
  function $(s, ctx=document){ return ctx.querySelector(s); }
  function $all(s, ctx=document){ return Array.from(ctx.querySelectorAll(s)); }
  const chartInstances = new WeakMap();

  function groupPairs(data){
    const groups = {};
    data.forEach(e=>{
      const key = `${e.base}-${e.target}`;
      groups[key] = groups[key] || [];
      groups[key].push({ x: e.ts*1000, y: e.rate });
    });
    for(const k in groups){ groups[k].sort((a,b)=>a.x-b.x); }
    return groups;
  }

  const timeFormatter = new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  });

  function formatRate(value){
    const n = Number(value);
    if(!Number.isFinite(n)) return value;
    if(n === 0) return '0';
    const abs = Math.abs(n);
    if(abs < 0.000001) return n.toExponential(6);
    if(abs < 1) return n.toFixed(8).replace(/0+$/, '').replace(/\.$/, '');
    if(abs < 1000) return n.toFixed(6).replace(/0+$/, '').replace(/\.$/, '');
    return n.toLocaleString(undefined, { maximumFractionDigits: 6 });
  }

  function shouldShowPointLabel(values, index){
    if(index === 0 || index === values.length - 1) return true;
    const current = Number(values[index]);
    const previous = Number(values[index - 1]);
    if(!Number.isFinite(current) || !Number.isFinite(previous) || previous === 0) return false;
    return Math.abs((current - previous) / previous) >= 0.0001;
  }

  function trendColor(values){
    const nums = values.map(Number).filter(Number.isFinite);
    if(nums.length < 2) return '#2563eb';
    const first = nums[0];
    const last = nums[nums.length - 1];
    if(first === 0) return '#2563eb';
    const change = (last - first) / first;
    if(change > 0.0001) return '#16a34a';
    if(change < -0.0001) return '#dc2626';
    return '#2563eb';
  }

  const pointValueLabels = {
    id: 'pointValueLabels',
    afterDatasetsDraw(chart) {
      const { ctx } = chart;
      ctx.save();
      ctx.font = '11px Arial, sans-serif';
      ctx.fillStyle = '#222';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'bottom';
      chart.data.datasets.forEach((dataset, datasetIndex) => {
        const meta = chart.getDatasetMeta(datasetIndex);
        if(meta.hidden) return;
        meta.data.forEach((element, index) => {
          const value = dataset.data[index];
          if(value == null) return;
          if(!shouldShowPointLabel(dataset.data, index)) return;
          const { x, y } = element.tooltipPosition();
          ctx.fillText(formatRate(value), x, y - 8);
        });
      });
      ctx.restore();
    }
  };

  const latestValueBadge = {
    id: 'latestValueBadge',
    afterDatasetsDraw(chart) {
      const { ctx, chartArea } = chart;
      const dataset = chart.data.datasets[0];
      if(!dataset || !dataset.data.length) return;
      const value = Number(dataset.data[dataset.data.length - 1]);
      if(!Number.isFinite(value)) return;
      const y = chart.scales.y.getPixelForValue(value);
      const color = dataset.borderColor || '#2563eb';
      const label = formatRate(value);
      ctx.save();
      ctx.setLineDash([5, 4]);
      ctx.strokeStyle = color;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(chartArea.left, y);
      ctx.lineTo(chartArea.right, y);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.font = 'bold 12px Arial, sans-serif';
      const paddingX = 8;
      const width = ctx.measureText(label).width + paddingX * 2;
      const height = 24;
      const x = Math.min(Math.max(chartArea.right - width - 8, chartArea.left), chartArea.right - width);
      const boxY = Math.max(chartArea.top, Math.min(y - height / 2, chartArea.bottom - height));
      ctx.fillStyle = color;
      ctx.fillRect(x, boxY, width, height);
      ctx.fillStyle = '#fff';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(label, x + width / 2, boxY + height / 2);
      ctx.restore();
    }
  };

  function chartAreaGradient(context){
    const chart = context.chart;
    const area = chart.chartArea;
    if(!area) return 'rgba(37, 99, 235, 0.18)';
    const color = chart.data.datasets[context.datasetIndex].borderColor || '#2563eb';
    const gradient = chart.ctx.createLinearGradient(0, area.top, 0, area.bottom);
    gradient.addColorStop(0, `${color}55`);
    gradient.addColorStop(1, `${color}08`);
    return gradient;
  }

  function buildTabs(container, pairs){
    const tabs = container.querySelector('.tabs-list');
    tabs.innerHTML = '';
    pairs.forEach((pair, idx)=>{
      const btn = document.createElement('button');
      btn.className = 'tab-btn';
      btn.textContent = `${pair.base}-${pair.target}`;
      btn.dataset.pair = pair.key;
      if(idx===0) btn.classList.add('active');
      tabs.appendChild(btn);
    });
  }

  function renderChart(canvas, dataset){
    const previousChart = chartInstances.get(canvas);
    if(previousChart) previousChart.destroy();
    const values = dataset.map(point => point.y);
    const color = trendColor(values);
    const chart = new Chart(canvas.getContext('2d'), {
      type: 'line',
      plugins: [pointValueLabels, latestValueBadge],
      data: {
        labels: dataset.map(point => timeFormatter.format(new Date(point.x))),
        datasets: [{ label: 'Rate', data: values, borderColor: color, backgroundColor: chartAreaGradient, fill: true, tension: 0.4, spanGaps:true, pointRadius: 2 }]
      },
      options: {
        normalized:true,
        plugins: {
          tooltip: {
            callbacks: {
              label: context => `${context.dataset.label}: ${formatRate(context.parsed.y)}`
            }
          }
        },
        scales:{
          x:{ ticks:{ maxRotation:0, autoSkip:true } },
          y:{ ticks:{ callback: value => formatRate(value) } }
        }
      }
    });
    chartInstances.set(canvas, chart);
    return chart;
  }

  function addEntryToUsdTable(table, entry){
    const rate = Number(entry.rate);
    if(!Number.isFinite(rate) || rate === 0) return;
    if(entry.base === 'USD') table[entry.target] = rate;
    if(entry.target === 'USD') table[entry.base] = 1 / rate;
  }

  function rateFromUsdTable(base, target, table){
    const basePerUsd = base === 'USD' ? 1 : table[base];
    const targetPerUsd = target === 'USD' ? 1 : table[target];
    if(!basePerUsd || !targetPerUsd) return null;
    return targetPerUsd / basePerUsd;
  }

  function deriveHistory(entries, base, target){
    if(base === target) {
      return [{ x: Date.now(), y: 1 }];
    }
    const direct = entries
      .filter(entry => entry.base === base && entry.target === target)
      .sort((a, b) => a.ts - b.ts)
      .map(entry => ({ x: entry.ts * 1000, y: entry.rate }));
    if(direct.length) return direct;

    const byTs = {};
    entries.forEach(entry => {
      byTs[entry.ts] = byTs[entry.ts] || {};
      addEntryToUsdTable(byTs[entry.ts], entry);
    });
    return Object.keys(byTs).sort((a, b) => Number(a) - Number(b)).map(ts => {
      const rate = rateFromUsdTable(base, target, byTs[ts]);
      return rate == null ? null : { x: Number(ts) * 1000, y: rate };
    }).filter(Boolean);
  }

  function pairUrlFromIndex(pair, indexUrl){
    return new URL(pair.file, indexUrl).toString();
  }

  async function loadAllPairEntries(indexUrl){
    const index = await fetch(indexUrl).then(r=>r.json());
    const pairs = index.pairs || [];
    const chunks = await Promise.all(pairs.map(pair => fetch(pairUrlFromIndex(pair, indexUrl)).then(r=>r.json()).catch(()=>[])));
    return { pairs, entries: chunks.flat() };
  }

  document.addEventListener('DOMContentLoaded', ()=>{
    $all('.exchange-control-chart').forEach(container=>{
      const indexUrl = container.dataset.ratesIndex;
      const baseSelect = container.querySelector('.exchange-base');
      const targetSelect = container.querySelector('.exchange-target');
      const status = container.querySelector('.exchange-status');
      const canvas = container.querySelector('.exchange-chart');
      let entries = [];

      function loadSelected(){
        const base = baseSelect.value;
        const target = targetSelect.value;
        const points = deriveHistory(entries, base, target);
        const chart = renderChart(canvas, points);
        chart.data.datasets[0].label = `${base} to ${target}`;
        chart.update();
        status.textContent = points.length ? `${points.length} point(s) loaded.` : `No ${base} to ${target} data found.`;
      }

      loadAllPairEntries(indexUrl).then(result=>{
        entries = result.entries;
        const currencies = Array.from(new Set(result.pairs.flatMap(pair => [pair.base, pair.target])));
        if(currencies.includes('USD')) {
          currencies.splice(currencies.indexOf('USD'), 1);
          currencies.unshift('USD');
        }
        baseSelect.innerHTML = currencies.map(code => `<option>${code}</option>`).join('');
        targetSelect.innerHTML = currencies.map(code => `<option>${code}</option>`).join('');
        baseSelect.value = 'USD';
        if(currencies.includes('VND')) targetSelect.value = 'VND';
        loadSelected();
      }).catch(err=>{
        console.error('Failed to load control chart data', err);
        status.textContent = 'Rates unavailable.';
      });

      container.querySelector('.exchange-load').addEventListener('click', loadSelected);
    });

    $all('.exchange-single-chart').forEach(container=>{
      const canvas = container.querySelector('.exchange-chart');
      if(!canvas || !container.dataset.pairHistory) return;
      try {
        const data = JSON.parse(container.dataset.pairHistory);
        const points = data.map(e => ({ x: e.ts*1000, y: e.rate }));
        renderChart(canvas, points);
      } catch (err) {
        console.error('Failed to render pair chart', err);
      }
    });

    const containers = $all('.exchange-tabs');
    containers.forEach(container=>{
      if(container.classList.contains('exchange-single-chart')) return;
      const indexUrl = container.dataset.ratesIndex;
      let lastTs = 0;
      const pairData = {};

      function pairUrl(pair){
        return new URL(pair.file, indexUrl).toString();
      }

      function loadPair(pair){
        return fetch(pairUrl(pair)).then(r=>r.json()).then(data=>{
          pairData[pair.key] = data.map(e => ({ x: e.ts*1000, y: e.rate }));
          return pairData[pair.key];
        });
      }

      function updateLastTs(){
        const all = Object.values(pairData).flat();
        if(all.length) lastTs = Math.max(...all.map(point => point.x));
      }

      function updateFromIndex(index){
        const pairs = index.pairs || [];
        buildTabs(container, pairs);
        const canvas = container.querySelector('.exchange-chart');
        const firstPair = pairs[0];
        if(!firstPair) return;

        loadPair(firstPair).then(points=>{
          renderChart(canvas, points);
          updateLastTs();
        });

        container.querySelector('.tabs-list').addEventListener('click', (ev)=>{
          const btn = ev.target.closest('.tab-btn');
          if(!btn) return;
          container.querySelectorAll('.tab-btn').forEach(b=>b.classList.remove('active'));
          btn.classList.add('active');
          const key = btn.dataset.pair;
          const pair = pairs.find(item => item.key === key);
          if(!pair) return;
          if(pairData[key]) {
            renderChart(canvas, pairData[key]);
          } else {
            loadPair(pair).then(points=>renderChart(canvas, points));
          }
        });
        return pairs;
      }

      fetch(indexUrl).then(r=>r.json()).then(index=>{
        updateFromIndex(index);
      }).catch(err=>{ console.error('Failed to load rates index', err); container.innerHTML = '<p>Rates unavailable</p>'; });

      // Poll JSON for updates every 30s and append new point(s)
      setInterval(()=>{
        fetch(indexUrl).then(r=>r.json()).then(index=>{
          const pairs = index.pairs || [];
          // find active pair
          const active = container.querySelector('.tab-btn.active');
          if(!active) return;
          const key = active.dataset.pair;
          const pair = pairs.find(item => item.key === key);
          if(!pair) return;
          return loadPair(pair).then(points=>{
          if(points.length && points[points.length-1].x > lastTs){
            const canvas = container.querySelector('.exchange-chart');
            // update chart with new data
            const chart = chartInstances.get(canvas);
            if(chart) {
              chart.data.labels = points.map(point => timeFormatter.format(new Date(point.x)));
              chart.data.datasets[0].data = points.map(point => point.y);
              chart.data.datasets[0].borderColor = trendColor(chart.data.datasets[0].data);
              chart.data.datasets[0].backgroundColor = chartAreaGradient;
              chart.update();
            } else {
              renderChart(canvas, points);
            }
            lastTs = points[points.length-1].x;
          }
          });
        }).catch(()=>{});
      }, 30000);
    });
  });
})();
