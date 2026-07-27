import { useState } from "react";
import {
  App,
  Button,
  Card,
  Col,
  Divider,
  Modal,
  Row,
  Slider,
  Space,
  Statistic,
  Tag,
  Typography,
} from "antd";
import {
  ArrowLeftOutlined,
  ArrowRightOutlined,
  CheckCircleOutlined,
  PlayCircleOutlined,
} from "@ant-design/icons";

import { useApprovals, useApproveAction, useWhatIf } from "../../api/hooks";
import type { PipelineState, Simulation } from "../../types/state";

const { Paragraph, Text, Title } = Typography;

interface Props {
  state?: PipelineState;
}

const DEFAULT_LEAD_TIME_DAYS = 16;

export default function TopRecommendation({ state }: Props) {
  const { message } = App.useApp();
  const actions = state?.recommendation?.structured_actions ?? [];
  const [index, setIndex] = useState(0);

  const [modalOpen, setModalOpen] = useState(false);
  const [safetyStock, setSafetyStock] = useState(0);
  const [altShare, setAltShare] = useState(0);
  const [leadTime, setLeadTime] = useState(DEFAULT_LEAD_TIME_DAYS);

  const whatIf = useWhatIf();
  const approve = useApproveAction();
  const { data: approvals } = useApprovals(state?.run_id);

  if (actions.length === 0) {
    return (
      <Card className="scd-card scd-recommendation-card" title="Top Recommendations" bordered={false}>
        <Paragraph type="secondary">
          Run analysis to generate ranked mitigation recommendations.
        </Paragraph>
      </Card>
    );
  }

  const action = actions[index % actions.length];
  const savings = state?.simulation?.revenue_loss_p50 ?? 0;
  const delay = state?.simulation?.recovery_time_days ?? 0;
  const confidence = Math.round(
    (state?.classifications?.[0]?.confidence ?? 0.75) * 100,
  );

  const isApproved = approvals?.some((item) => item.action_index === index) ?? false;

  const handleApprove = () => {
    if (!state?.run_id) {
      message.warning("Run analysis first to approve an action");
      return;
    }
    approve.mutate(
      {
        run_id: state.run_id,
        action_index: index,
        action_text: action.action,
        owner: action.owner,
      },
      {
        onSuccess: () => message.success("Action approved"),
        onError: () => message.error("Failed to approve action"),
      },
    );
  };

  const openWhatIf = () => {
    whatIf.reset();
    setSafetyStock(0);
    setAltShare(0);
    setLeadTime(DEFAULT_LEAD_TIME_DAYS);
    setModalOpen(true);
  };

  const runWhatIf = () => {
    whatIf.mutate({
      classifications: state?.classifications ?? [],
      impacts: state?.impacts ?? [],
      forecast: state?.forecast ?? null,
      overrides: {
        safety_stock_days: safetyStock,
        alt_supplier_share_pct: altShare,
        lead_time_mean_days: leadTime,
      },
    });
  };

  const baseline = state?.simulation;
  const result = whatIf.data;

  return (
    <Card
      className="scd-card scd-recommendation-card"
      title="Top Recommendations"
      bordered={false}
      extra={
        <Text type="secondary">
          {index + 1} of {actions.length}
        </Text>
      }
    >
      <Title level={4} style={{ marginTop: 0 }}>
        {action.action}
      </Title>
      <Paragraph type="secondary">{state?.recommendation?.summary}</Paragraph>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={8}>
          <Statistic title="Savings" value={savings} prefix="$" precision={0} />
        </Col>
        <Col span={8}>
          <Statistic title="Delay Reduction" value={Math.max(0, 14 - delay)} suffix=" days" />
        </Col>
        <Col span={8}>
          <Statistic title="Confidence" value={confidence} suffix="%" />
        </Col>
      </Row>
      <Space wrap>
        <Button
          type="primary"
          icon={<PlayCircleOutlined />}
          style={{ background: "#389e0d" }}
          onClick={openWhatIf}
        >
          Run What-if
        </Button>
        {isApproved ? (
          <Tag color="success" icon={<CheckCircleOutlined />} style={{ padding: "4px 10px" }}>
            Approved
          </Tag>
        ) : (
          <Button
            icon={<CheckCircleOutlined />}
            loading={approve.isPending}
            onClick={handleApprove}
          >
            Approve Action
          </Button>
        )}
        <Button
          icon={<ArrowLeftOutlined />}
          onClick={() => setIndex((value) => (value - 1 + actions.length) % actions.length)}
        />
        <Button
          icon={<ArrowRightOutlined />}
          onClick={() => setIndex((value) => (value + 1) % actions.length)}
        />
      </Space>

      <Modal
        title="What-if simulation"
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        okText="Run simulation"
        okButtonProps={{ loading: whatIf.isPending }}
        onOk={runWhatIf}
        cancelText="Close"
      >
        <Paragraph type="secondary">
          Adjust mitigation levers and re-run the Monte Carlo simulation to compare the
          outcome against the current run.
        </Paragraph>

        <Text strong>Extra safety stock: {safetyStock} days</Text>
        <Slider min={0} max={30} value={safetyStock} onChange={setSafetyStock} />

        <Text strong>Volume shifted to alternate supplier: {altShare}%</Text>
        <Slider min={0} max={100} value={altShare} onChange={setAltShare} />

        <Text strong>Supplier lead time: {leadTime} days</Text>
        <Slider min={4} max={30} value={leadTime} onChange={setLeadTime} />

        {result && (
          <>
            <Divider style={{ margin: "16px 0" }} />
            <Row gutter={16}>
              <Col span={12}>
                <Text type="secondary">Baseline</Text>
                {renderSimStats(baseline)}
              </Col>
              <Col span={12}>
                <Text type="secondary">What-if</Text>
                {renderSimStats(result, baseline)}
              </Col>
            </Row>
          </>
        )}
      </Modal>
    </Card>
  );
}

function renderSimStats(sim?: Simulation | null, baseline?: Simulation | null) {
  if (!sim) {
    return (
      <Paragraph type="secondary" style={{ marginTop: 8 }}>
        No data
      </Paragraph>
    );
  }
  const improved = (value: number, base?: number) =>
    base === undefined ? undefined : value < base ? { color: "#389e0d" } : value > base ? { color: "#cf1322" } : undefined;

  return (
    <Space direction="vertical" style={{ marginTop: 8 }}>
      <Statistic
        title="Stockout probability"
        value={Math.round(sim.stockout_probability * 100)}
        suffix="%"
        valueStyle={improved(sim.stockout_probability, baseline?.stockout_probability)}
      />
      <Statistic
        title="Revenue loss (P50)"
        value={sim.revenue_loss_p50}
        prefix="$"
        precision={0}
        valueStyle={improved(sim.revenue_loss_p50, baseline?.revenue_loss_p50)}
      />
      <Statistic
        title="Recovery time"
        value={sim.recovery_time_days}
        suffix=" days"
        precision={1}
        valueStyle={improved(sim.recovery_time_days, baseline?.recovery_time_days)}
      />
    </Space>
  );
}
